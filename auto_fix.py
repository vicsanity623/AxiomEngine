"""Auto Scan & Fix - Unified Orchestrator for Ruff and Mypy"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

import ollama

MODEL = "qwen2.5-coder:7b-instruct"
MEMORY_FILE = "MEMORY.md"

SYSTEM_PROMPT = """You are an expert Python Mypy type-hint fixer.
You MUST respond EXCLUSIVELY with <THOUGHT> (optional) and <EDIT> blocks.
Never output any text, markdown, explanations, or code blocks outside these tags.

Rules:
- <SEARCH> must be EXACT verbatim copy-paste from MEMORY.md (every space, tab, blank line, exact indentation).
- ALWAYS include 1-2 lines BEFORE and AFTER the changed section in <SEARCH> to ensure context.
- <REPLACE> must keep THE EXACT SAME indentation level as the original.
- CRITICAL: A single <EDIT> block MUST represent a CONTINUOUS, CONTIGUOUS block of lines from the source file.
- NEVER use `...` to skip lines in your <SEARCH> or <REPLACE> blocks. You must write out every single line.
- If you need to change lines in different parts of the file, you MUST use MULTIPLE SEPARATE <EDIT> blocks.

CRITICAL FOCUS RULE - VIOLATION CAUSES IMMEDIATE FAILURE:
- Fix ONLY the EXACT Mypy error reported in "Error to fix:".
- Your <SEARCH> MUST be the contiguous block from MEMORY.md that contains the targeted code.
- Do NOT edit any code that is not directly causing the reported error.
- For "Statement is unreachable [unreachable]", simply delete the dead code block. Do not add guards, refactor logic, or touch unrelated variables.
- For any other error, make the minimal change needed to satisfy mypy at that exact location.
- NEVER add defensive code, null checks, or "if topic_filter" unless the error explicitly mentions it.
- The change must be surgical — one small contiguous edit that resolves the error and nothing else."""

USER_PROMPT_TEMPLATE = """Fix ONLY the Mypy error(s) shown below in the file {filepath}

Respond **EXCLUSIVELY** with:
- Zero or one <THOUGHT>single short sentence describing the rule being fixed</THOUGHT>
- One or more complete <EDIT> blocks in this exact nested format — NOTHING else

<EDIT path="{filepath}">
<SEARCH>
exact verbatim contiguous lines copied from MEMORY.md INCLUDING ALL leading whitespace
</SEARCH>
<REPLACE>
fixed lines keeping THE EXACT SAME indentation level
</REPLACE>
</EDIT>

CRITICAL RULES YOU MUST OBEY:
- One <EDIT> block per contiguous chunk of code.
- If you need to add an import AND change code, use TWO SEPARATE <EDIT> blocks with the import block FIRST.
- <SEARCH> must be EXACT copy-paste from MEMORY.md (every space, tab, blank line).
- NEVER skip lines with '...' or combine non-adjacent lines. You will fail if you use `...`.
- NEVER include linter artifacts (like line numbers) in your <SEARCH> block.
- ALWAYS include 1-2 lines BEFORE and AFTER the changed line in <SEARCH>.
- NO text, NO markdown, NO explanations outside the XML tags.

Error to fix:
{error_text}
{anchoring_hint}

Use the exact file path in the <EDIT> tag: {filepath}
"""


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Auto Scan & Fix - Unified Orchestrator for Ruff and Mypy"
    )
    parser.add_argument(
        "--exclude",
        "-e",
        action="append",
        default=[],
        help="Path to file or directory to exclude from checks (can be used multiple times).",
    )
    return parser.parse_args()


def load_memory(memory_file_path):
    """Load content from MEMORY_FILE."""
    if not os.path.exists(memory_file_path):
        return None
    try:
        with open(memory_file_path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[SYSTEM] ❌ Error reading memory file {memory_file_path}: {e}")
        return None


def extract_snippet(
    filepath: str,
    error_text: str,
    context_window: int = 15,  # Reduced to keep 7B model highly focused
    max_total_lines: int = 20,
) -> tuple[str, str]:
    """Parse error text for line numbers and extract a highly targeted window + the exact line text."""
    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[SYSTEM] ❌ Could not read {filepath}: {e}")
        return "", ""

    pattern = re.compile(
        r"(?m)^\s*(\d+)\s*\||:(\d+)(?::\d+)?|line\s+(\d+)", re.IGNORECASE
    )

    found_nums = []
    for match in pattern.finditer(error_text):
        for i in (1, 2, 3):
            val = match.group(i)
            if val:
                found_nums.append(int(val))

    valid_lines = []
    for num in found_nums:
        if 1 <= num <= len(lines) and num not in valid_lines:
            valid_lines.append(num)

    if not valid_lines:
        print(
            f"[SYSTEM] ⚠️ Could not detect valid line numbers. Loading first {max_total_lines} lines as fallback."
        )
        return "".join(lines[:max_total_lines]), ""

    min_line = min(valid_lines)
    max_line = max(valid_lines)

    max_spread = max_total_lines - (2 * context_window)
    if (max_line - min_line) > max_spread:
        primary = valid_lines[0]
        print(
            f"[SYSTEM] ⚠️ Line number spread too large ({max_line - min_line} lines). Anchoring around primary line {primary}."
        )
        half_spread = max_spread // 2
        min_line = max(1, primary - half_spread)
        max_line = min(len(lines), primary + half_spread)

    start_idx = max(0, min_line - 1 - context_window)
    end_idx = min(len(lines), max_line + context_window)

    snippet = "".join(lines[start_idx:end_idx])
    print(
        f"[SYSTEM] ✂️  Extracted targeted snippet (lines {start_idx + 1} to {end_idx}) for memory context."
    )

    # Extract the exact text of the line causing the error to anchor the AI
    target_line_text = ""
    primary_idx = valid_lines[0] - 1
    if 0 <= primary_idx < len(lines):
        target_line_text = lines[primary_idx].strip()

    return snippet, target_line_text


def update_memory_file(filepath: str, file_content: str) -> bool:
    """Add or update a file's content in MEMORY.md."""
    memory_md_content = ""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, encoding="utf-8") as f:
            memory_md_content = f.read()

    file_block_header = f"## File Contents: {filepath}"
    new_file_block = f"{file_block_header}\n```python\n{file_content}\n```\n"

    existing_block_pattern = re.compile(
        r"## File Contents: "
        + re.escape(filepath)
        + r"\n```python\n(.*?)\n```\n",
        re.DOTALL,
    )
    existing_block_match = existing_block_pattern.search(memory_md_content)

    if existing_block_match:
        existing_content = existing_block_match.group(1)
        if existing_content.strip() == file_content.strip():
            return False
        print(
            f"[SYSTEM] 🔄 Updating snippet for '{filepath}' in {MEMORY_FILE}..."
        )
        memory_md_content = existing_block_pattern.sub(
            lambda m: new_file_block, memory_md_content, count=1
        )
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            f.write(memory_md_content)
        return True

    print(f"[SYSTEM] + Adding snippet for '{filepath}' to {MEMORY_FILE}...")
    if not memory_md_content.strip():
        memory_md_content = (
            "# AI Memory Store\n\n"
            "This file contains targeted snippets for the AI to reference when performing tasks.\n"
            "It is automatically loaded into the AI's memory at startup.\n\n---\n\n"
        )
    else:
        memory_md_content += "\n---\n\n"

    memory_md_content += new_file_block
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(memory_md_content)
    return True


def flexible_replace(content: str, search_text: str, replace_text: str):
    """Attempt to find and replace text, fall back to an indentation-agnostic match."""
    if search_text in content:
        return content.replace(search_text, replace_text, 1)

    search_lines = search_text.splitlines()
    while search_lines and not search_lines[0].strip():
        search_lines.pop(0)
    while search_lines and not search_lines[-1].strip():
        search_lines.pop()

    if not search_lines:
        return None

    content_lines = content.splitlines(keepends=True)
    search_len = len(search_lines)

    match_idx = -1
    for i in range(len(content_lines) - search_len + 1):
        window = content_lines[i : i + search_len]
        if all(
            window[j].strip() == search_lines[j].strip()
            for j in range(search_len)
        ):
            match_idx = i
            break

    if match_idx == -1:
        return None

    window = content_lines[match_idx : match_idx + search_len]

    orig_indent = ""
    search_indent = ""
    for j in range(search_len):
        if search_lines[j].strip():
            orig_line = window[j]
            match_orig = re.match(r"^([ \t]*)", orig_line)
            orig_indent = match_orig.group(1) if match_orig else ""

            match_search = re.match(r"^([ \t]*)", search_lines[j])
            search_indent = match_search.group(1) if match_search else ""
            break

    replace_lines = replace_text.splitlines()
    while replace_lines and not replace_lines[0].strip():
        replace_lines.pop(0)
    while replace_lines and not replace_lines[-1].strip():
        replace_lines.pop()

    adjusted_replace_lines = []
    newline_char = "\r\n" if "\r\n" in content else "\n"

    for rline in replace_lines:
        if not rline.strip():
            adjusted_replace_lines.append(newline_char)
            continue

        if rline.startswith(search_indent):
            adjusted_line = orig_indent + rline[len(search_indent) :]
        else:
            adjusted_line = orig_indent + rline.lstrip(" \t")

        adjusted_replace_lines.append(adjusted_line + newline_char)

    if (
        window
        and not window[-1].endswith(("\r", "\n"))
        and adjusted_replace_lines
    ):
        adjusted_replace_lines[-1] = adjusted_replace_lines[-1].rstrip("\r\n")

    before = content_lines[:match_idx]
    after = content_lines[match_idx + search_len :]

    return "".join(before + adjusted_replace_lines + after)


def apply_edits(response_text, detected_filepath=None):
    """Apply search and replace edits and return the number of edits and dict of backups."""
    pattern = re.compile(
        r'<EDIT path="(.*?)">\s*<SEARCH>\n?(.*?)\n?</SEARCH>\s*<REPLACE>\n?(.*?)\n?</REPLACE>\s*</EDIT>',
        re.DOTALL,
    )
    matches = pattern.finditer(response_text)
    edits_made = 0
    found_any_edit_block = False
    backups = {}

    for match in matches:
        found_any_edit_block = True
        filepath = match.group(1).strip()
        search_text = match.group(2)
        replace_text = match.group(3)

        if not os.path.exists(filepath):
            print(f"\n[SYSTEM] ❌ Error: Could not find file at {filepath}")
            continue

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            new_content = flexible_replace(content, search_text, replace_text)

            if new_content is not None:
                if new_content != content:
                    # Save a backup of the original state in case Ruff fails
                    if filepath not in backups:
                        backups[filepath] = content

                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"\n[SYSTEM] ✅ Successfully patched: {filepath}")
                    edits_made += 1
                else:
                    print(
                        f"\n[SYSTEM] ⚠️ Search block found, but resulted in no changes for: {filepath}"
                    )
            else:
                print(
                    f"\n[SYSTEM] ⚠️ Could not find exact or flexible <SEARCH> block in {filepath}."
                )
                print(
                    "   Likely context mismatch or the file has drastically changed."
                )
        except Exception as e:
            print(f"\n[SYSTEM] ❌ Failed to read/write {filepath}: {e}")

    if not found_any_edit_block:
        print("\n[SYSTEM] ⚠️ No valid <EDIT> blocks found. No changes applied.")

    return edits_made, backups


def format_bandwidth(total_bytes: int) -> str:
    """Format bytes into KB, MB, GB."""
    if total_bytes < 1024:
        return f"{total_bytes} B"
    if total_bytes < 1024 * 1024:
        return f"{total_bytes / 1024:.2f} KB"
    if total_bytes < 1024 * 1024 * 1024:
        return f"{total_bytes / (1024 * 1024):.2f} MB"
    return f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"


def run_ruff_checks(excludes: list[str] | None = None) -> bool:
    """Run Ruff checks to act as a gatekeeper. Returns True if codebase is clean."""
    excludes = excludes or []

    print(
        "[SYSTEM] 🧹 Verifying codebase with 'ruff format .' and 'ruff check' ..."
    )

    format_cmd = [sys.executable, "-m", "ruff", "format", "."]
    check_cmd = [sys.executable, "-m", "ruff", "check"]

    for exc in excludes:
        format_cmd.extend(["--exclude", exc])
        check_cmd.extend(["--exclude", exc])

    subprocess.run(format_cmd, capture_output=True)  # noqa: S603

    result = subprocess.run(check_cmd, capture_output=True, text=True)  # noqa: S603
    stdout = result.stdout.strip()

    return bool(
        not stdout or result.returncode == 0 or "Found 0 errors" in stdout
    )


def get_next_mypy_error(excludes: list[str] | None = None):
    """Run Mypy check, ignore excluded files/dirs, and parse output for the first error."""
    excludes = excludes or []

    # Permanently exclude our own mypy annotation tool (it cannot be tampered with
    # during the auto-fix process). This is enforced at the mypy CLI level,
    # exactly like .gitignore protects files from git.
    mypy_annotate_path = "tools/mypy_annotate.py"
    if mypy_annotate_path not in excludes:
        excludes.append(mypy_annotate_path)

    print("[SYSTEM] 🔍 Running 'mypy' checks ...")
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "mypy",
            ".",
            "--show-error-end",
            "--platform",
            "darwin",
            "--exclude",
            mypy_annotate_path,  # <-- this makes mypy completely ignore the file
        ],
        capture_output=True,
        text=True,
    )

    stdout = result.stdout.strip()

    if not stdout or "Success: no issues found" in stdout:
        return None, None

    lines = stdout.splitlines()

    for line in lines:
        line = line.strip()
        match = re.search(r"^([a-zA-Z0-9_/\.\-\\]+\.py):\d+:.*?error:.*", line)

        if match:
            filepath = os.path.abspath(match.group(1))

            # Check if this file falls under any of our exclusions
            is_excluded = False
            for exc in excludes:
                abs_exc = os.path.abspath(exc)
                # Exact file match OR directory match
                if filepath == abs_exc or filepath.startswith(
                    abs_exc + os.sep
                ):
                    is_excluded = True
                    break

            if is_excluded:
                continue  # Silently skip this error and check the next one

            return filepath, line

    return None, None


def main():
    """Unified Orchestrator: Auto-Runs smart_coder.py, then handles Mypy with safety reverts."""
    args = parse_args()
    excludes = args.exclude

    print(f"🚀 Auto Scan & Fix Initialized (Model: {MODEL})")
    print(
        "Workflow: Run smart_coder.py -> Check Ruff -> Fix Mypy -> Test Fix -> Revert if Broken -> Loop."
    )
    if excludes:
        print(f"🚫 Excluding paths: {', '.join(excludes)}\n")

    consecutive_failures = 0
    last_error_text = ""

    while True:
        try:
            print("\n" + "=" * 70)

            # --- TASK 1: Run smart_coder.py ---
            if os.path.exists("smart_coder.py"):
                print(
                    "[SYSTEM] 🚀 Task 1: Running smart_coder.py to automatically fix Ruff errors..."
                )
                subprocess.run([sys.executable, "smart_coder.py"])  # noqa: S603
            else:
                print(
                    "[SYSTEM] ⚠️ smart_coder.py not found in current directory. Skipping Task 1."
                )

            if os.path.exists(MEMORY_FILE):
                os.remove(MEMORY_FILE)
                print("[SYSTEM] 🧹 Wiped MEMORY.md for a fresh session.")

            if not run_ruff_checks(excludes):
                print(
                    "\n[SYSTEM] ❌ ABORTING: Ruff check failed even after Task 1!"
                )
                print(
                    "There are unrecoverable Ruff errors in the codebase. Please fix them manually."
                )
                break

            # --- TASK 2: Mypy Checks & Fixes ---
            filepath, error_text = get_next_mypy_error(excludes)

            if not filepath or not error_text:
                print(
                    "\n🎉 [SYSTEM] ALL CLEAR! No valid Mypy errors found. Your codebase is fully typed!"
                )
                break

            # Check for identical repeating errors BEFORE attempting a fix
            if error_text == last_error_text:
                consecutive_failures += 1
            else:
                consecutive_failures = 0
                last_error_text = error_text

            if consecutive_failures >= 3:
                print(
                    "\n[SYSTEM] ❌ STOPPING: Script failed to resolve this exact error 3 times in a row."
                )
                print("Manual intervention required for:")
                print(error_text)
                break

            if "Library stubs not installed for" in error_text:
                lib_match = re.search(
                    r'Library stubs not installed for "([^"]+)"', error_text
                )
                if lib_match:
                    lib = lib_match.group(1)
                    print(
                        f"\n[SYSTEM] 🛠️ Missing Stub Detected! Auto-installing missing stubs for '{lib}'..."
                    )
                    try:
                        uv_path = shutil.which("uv")
                        if not uv_path:
                            raise FileNotFoundError("uv not found on PATH")

                        # Force uv to install to the exact environment executing this script (crucial for Conda)
                        subprocess.run(  # noqa: S603
                            [
                                uv_path,
                                "pip",
                                "install",
                                "--python",
                                sys.executable,
                                f"types-{lib}",
                            ],
                            check=True,
                        )
                    except Exception as e:
                        print(
                            f"[SYSTEM] ⚠️ 'uv pip' failed ({e}), falling back to standard pip..."
                        )
                        subprocess.run(  # noqa: S603
                            [
                                sys.executable,
                                "-m",
                                "pip",
                                "install",
                                f"types-{lib}",
                            ]
                        )

                    # Native Safety Net: Let Mypy install types on its own just in case pip missed the env
                    subprocess.run(  # noqa: S603
                        [
                            sys.executable,
                            "-m",
                            "mypy",
                            "--install-types",
                            "--non-interactive",
                            ".",
                        ],
                        capture_output=True,
                    )

                    print(
                        "[SYSTEM] ⏳ Waiting 2 seconds for environment to update..."
                    )
                    time.sleep(2)
                    continue

            print("\n[SYSTEM] Found Mypy Error:")
            print(f"> {error_text}\n")

            snippet_text, target_line_text = extract_snippet(
                filepath, error_text
            )

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if update_memory_file(filepath, snippet_text):
                reloaded = load_memory(MEMORY_FILE)
                messages.insert(
                    1,
                    {
                        "role": "system",
                        "content": f"Memory loaded:\n\n{reloaded}",
                    },
                )
                time.sleep(1.0)

            # Inform the AI exactly what code it should be looking for
            if target_line_text:
                anchoring_hint = (
                    f"\nHint: The error is triggered on or around this exact line of code:\n"
                    f"`{target_line_text}`\n"
                    f"Make sure this exact line is included inside your <SEARCH> block."
                )
            else:
                anchoring_hint = ""

            full_prompt = USER_PROMPT_TEMPLATE.format(
                filepath=filepath,
                error_text=error_text,
                anchoring_hint=anchoring_hint,
            )

            reinforcement = f"""CRITICAL ONE-PASS INSTRUCTIONS (MUST OBEY OR YOU FAIL):
1. Your entire response MUST consist ONLY of <THOUGHT> and <EDIT> tags. Nothing else.
2. Fix ONLY the reported error at the exact line shown: {error_text}
3. Your <SEARCH> block MUST NEVER use `...` to skip lines. It must be a 100% exact copy of a continuous block from MEMORY.md.
4. For unreachable errors, delete the dead code. Do not add if-statements or change unrelated code.
5. IMPORT-FIRST RULE: If a typing import is needed, the FIRST <EDIT> block MUST add the import. Only then the second <EDIT> for the fix.
6. Example for unreachable error (follow this exact style):

<THOUGHT>Remove unreachable statement after return</THOUGHT>
<EDIT path="{filepath}">
<SEARCH>
    return result
    print("This will never run")
</SEARCH>
<REPLACE>
    return result
</REPLACE>
</EDIT>

Do not deviate. Stay surgical. Any unrelated change or hallucinated `...` will cause the patch to fail."""

            messages.append({"role": "user", "content": full_prompt})
            messages.append({"role": "user", "content": reinforcement})

            print("AI: \n", end="", flush=True)
            response_text = ""

            prompt_tokens = 0
            completion_tokens = 0
            start_time = time.time()

            try:
                stream = ollama.chat(
                    model=MODEL, messages=messages, stream=True
                )
                for chunk in stream:
                    content = chunk.get("message", {}).get("content", "")
                    print(content, end="", flush=True)
                    response_text += content

                    if chunk.get("done"):
                        prompt_tokens = chunk.get("prompt_eval_count", 0)
                        completion_tokens = chunk.get("eval_count", 0)
                print()
            except Exception as e:
                err_msg = str(e).lower()
                if "connection refused" in err_msg or "errno 61" in err_msg:
                    print(
                        "\n\n[SYSTEM] ❌ ERROR: Ollama connection refused. Is the Ollama server running?"
                    )
                    break
                raise e

            end_time = time.time()
            elapsed_time = end_time - start_time
            total_tokens = prompt_tokens + completion_tokens

            req_bytes = sum(
                len(m.get("content", "").encode("utf-8")) for m in messages
            )
            res_bytes = len(response_text.encode("utf-8"))
            total_bytes = req_bytes + res_bytes
            bw_str = format_bandwidth(total_bytes)

            edits_made, backups = apply_edits(
                response_text, detected_filepath=filepath
            )

            print(
                f"\n[STATS] ⏱️  Time Elapsed: {elapsed_time:.1f}s | 🪙  Total Tokens: {total_tokens} (Prompt: {prompt_tokens}, Completion: {completion_tokens}) | 📶 Bandwidth Used: {bw_str}"
            )

            if edits_made > 0:
                print(
                    "\n[SYSTEM] ⏳ Mypy fix applied. Verifying if changes broke Ruff formatting/linting..."
                )

                if not run_ruff_checks(excludes):
                    print(
                        "\n[SYSTEM] ⚠️ Edit introduced Ruff errors! Reverting changes..."
                    )
                    for bp_path, orig_content in backups.items():
                        try:
                            with open(bp_path, "w", encoding="utf-8") as f:
                                f.write(orig_content)
                            print(f"[SYSTEM] 🔄 Reverted {bp_path}")
                        except Exception as e:
                            print(
                                f"[SYSTEM] ❌ Failed to revert {bp_path}: {e}"
                            )

                    print(
                        "[SYSTEM] 🧹 Re-running Ruff format/check to ensure clean undo state..."
                    )
                    run_ruff_checks(excludes)
                    print("[SYSTEM] ⏳ Waiting 2 seconds before next cycle...")
                    time.sleep(2)
                else:
                    print(
                        "\n[SYSTEM] ✅ All checks passed! Waiting 3 seconds before next cycle to ensure disk sync..."
                    )
                    time.sleep(3)
            else:
                print(
                    "\n[SYSTEM] ⚠️ No edits successfully applied. Re-looping in 2 seconds..."
                )
                time.sleep(2)

        except KeyboardInterrupt:
            print("\n[SYSTEM] Interrupted by user.")
            break
        except Exception as e:
            print(f"\n[ERROR] {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
