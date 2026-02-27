"""Smart Coder - Guided Linter Fixer"""

import os
import re
import sys
import time

import ollama

MODEL = "qwen2.5-coder:7b-instruct"
MEMORY_FILE = "MEMORY.md"

# Strict system prompt (rules the model must always follow)
SYSTEM_PROMPT = """You are an expert Python linter fixer.
You MUST respond EXCLUSIVELY with <THOUGHT> (optional) and <EDIT> blocks.
Never output any text, markdown, explanations, or code blocks outside these tags.

Rules:
- One <EDIT> per atomic change
- <SEARCH> must be EXACT verbatim copy-paste from MEMORY.md (every space, tab, blank line, exact indentation)
- ALWAYS include 1-2 lines BEFORE and AFTER the changed section in <SEARCH>
- <REPLACE> must keep THE EXACT SAME indentation level as the original
- Module-level code (classes, functions) must start with ZERO leading spaces
- Docstrings: imperative mood for the first line
- The script will completely ignore your response if format is wrong."""

# User prompt template (gets formatted with real file + error)
USER_PROMPT_TEMPLATE = """Fix ONLY the Ruff / mypy error(s) shown below in the file {filepath}

Respond **EXCLUSIVELY** with:
- Zero or one <THOUGHT>single short sentence describing the rule being fixed</THOUGHT>
- One or more complete <EDIT> blocks in this exact nested format — NOTHING else

<EDIT path="{filepath}">
<SEARCH>
exact verbatim lines copied from MEMORY.md INCLUDING ALL leading whitespace/indentation
</SEARCH>
<REPLACE>
fixed lines keeping THE EXACT SAME indentation level
</REPLACE>
</EDIT>

CRITICAL RULES YOU MUST OBEY:
- One <EDIT> block per atomic change
- <SEARCH> must be EXACT copy-paste from the MEMORY.md file (every space, tab, blank line)
- ALWAYS include 1-2 lines BEFORE and AFTER the changed line in <SEARCH>
- Module-level code (classes, functions) must start with ZERO leading spaces in <SEARCH> and <REPLACE>
- NEVER dedent, clean, or reformat the <SEARCH> block
- Docstrings: imperative mood for the first line
- NO text, NO markdown, NO lists, NO explanations, NO ```python outside the tags

The script will ignore your entire response if you deviate.

Error to fix:
{error_text}

Use the exact file path in the <EDIT> tag: {filepath}
"""


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
    filepath: str, error_text: str, context_window: int = 25
) -> str:
    """Parse error text for line numbers and extract a specific window from the file."""
    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[SYSTEM] ❌ Could not read {filepath}: {e}")
        return ""

    line_numbers = set()

    # Pattern 1: Standard linter format (e.g., file.py:82:8 or file.py:82:)
    for match in re.finditer(r":(\d+)(?::\d+)?", error_text):
        line_numbers.add(int(match.group(1)))

    # Pattern 2: Ruff / Rust visual context (e.g., " 82 | ")
    for match in re.finditer(r"(?m)^\s*(\d+)\s*\|", error_text):
        line_numbers.add(int(match.group(1)))

    # Pattern 3: Traceback format (e.g., "line 82")
    for match in re.finditer(r"line\s+(\d+)", error_text, re.IGNORECASE):
        line_numbers.add(int(match.group(1)))

    if not line_numbers:
        print(
            "[SYSTEM] ⚠️ Could not detect line numbers in error. Loading full file into memory."
        )
        return "".join(lines)

    min_line = max(1, min(line_numbers))
    max_line = min(len(lines), max(line_numbers))

    start_idx = max(0, min_line - 1 - context_window)
    end_idx = min(len(lines), max_line + context_window)

    snippet = "".join(lines[start_idx:end_idx])
    print(
        f"[SYSTEM] ✂️  Extracted targeted snippet (lines {start_idx + 1} to {end_idx}) for memory context."
    )
    return snippet


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
    """Attempts to find and replace text, falling back to an indentation-agnostic match."""
    # 1. Try exact match first
    if search_text in content:
        return content.replace(search_text, replace_text, 1)

    # 2. Fallback: Try flexible match ignoring exact leading/trailing blank lines and indentations
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
        # Compare ignoring leading/trailing whitespace
        if all(
            window[j].strip() == search_lines[j].strip()
            for j in range(search_len)
        ):
            match_idx = i
            break

    if match_idx == -1:
        return None

    # Match found! Calculate the base indentation to adapt the replacement text
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

        # Re-indent based on the calculated delta
        if rline.startswith(search_indent):
            adjusted_line = orig_indent + rline[len(search_indent) :]
        else:
            adjusted_line = orig_indent + rline.lstrip(" \t")

        adjusted_replace_lines.append(adjusted_line + newline_char)

    # Try to retain original file's newline style for the end of the block
    if window and not window[-1].endswith(("\r", "\n")) and adjusted_replace_lines:
        adjusted_replace_lines[-1] = adjusted_replace_lines[-1].rstrip(
            "\r\n"
        )

    before = content_lines[:match_idx]
    after = content_lines[match_idx + search_len :]

    return "".join(before + adjusted_replace_lines + after)


def apply_edits(response_text, detected_filepath=None):
    """Apply search and replace edits based on AI response."""
    pattern = re.compile(
        r'<EDIT path="(.*?)">\s*<SEARCH>\n?(.*?)\n?</SEARCH>\s*<REPLACE>\n?(.*?)\n?</REPLACE>\s*</EDIT>',
        re.DOTALL,
    )
    matches = pattern.finditer(response_text)
    edits_made = 0
    found_any_edit_block = False

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

            # Attempt replacement with robust fallback
            new_content = flexible_replace(content, search_text, replace_text)

            if new_content is not None:
                if new_content != content:
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
                print(
                    f"   Provided <SEARCH> (first 400 chars):\n---\n{search_text[:400]}\n---"
                )
        except Exception as e:
            print(f"\n[SYSTEM] ❌ Failed to read/write {filepath}: {e}")

    if not found_any_edit_block:
        raw_code_block_pattern = re.compile(
            r"```python\n(.*?)\n```", re.DOTALL
        )
        if raw_code_block_pattern.search(response_text):
            print(
                "\n[SYSTEM] ❌ AI output plain code block(s) instead of <EDIT> format."
            )
            print("   No changes applied.")
        else:
            print("\n[SYSTEM] ⚠️ No <EDIT> blocks found. No changes applied.")

    return edits_made


def main():
    """Run script to edit files according to AI response."""
    # === FRESH MEMORY ON EVERY RUN ===
    if os.path.exists(MEMORY_FILE):
        os.remove(MEMORY_FILE)
        print("[SYSTEM] 🧹 Wiped MEMORY.md for a fresh session.")

    print(f"🚀 Smart Coder Initialized (Model: {MODEL})")
    print("Guided mode: file path → error → auto patch.\n")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("[SYSTEM] 🧠 Fresh memory session started.")

    while True:
        try:
            print("\n" + "=" * 70)
            print("Enter the FULL path to the Python file to fix")
            print(
                "Press Ctrl+D on a blank line when done.\n> ",
                end="",
                flush=True,
            )

            filepath_input = sys.stdin.read().strip()
            if not filepath_input or filepath_input.lower() in [
                "exit",
                "quit",
            ]:
                print("\nExiting.")
                break

            if not os.path.isfile(filepath_input):
                print(f"[SYSTEM] ❌ File not found: {filepath_input}")
                continue

            filepath = os.path.abspath(filepath_input)
            print(f"[SYSTEM] Using file: {filepath}")

            # --- DELAYED MEMORY CREATION ---
            # Wait for user to input error text first before loading into memory.
            print(
                "\nPaste the FULL error / lint output to fix (multi-line OK)"
            )
            print(
                "Press Ctrl+D on a blank line when finished.\n> ",
                end="",
                flush=True,
            )

            error_text = sys.stdin.read().strip()
            if not error_text:
                print("[SYSTEM] No error provided. Skipping.")
                continue

            # Extract just the snippet relevant to the line numbers in the error
            snippet_text = extract_snippet(filepath, error_text)

            # Update memory only with the focused snippet
            if update_memory_file(filepath, snippet_text):
                print(
                    "[SYSTEM] Memory loaded with targeted snippet. Reloading context..."
                )
                reloaded = load_memory(MEMORY_FILE)
                if messages and "Memory loaded:" in messages[0]["content"]:
                    messages.pop(0)
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": f"Memory loaded:\n\n{reloaded}",
                    },
                )
                time.sleep(1.0)

            # Build full prompt
            full_prompt = USER_PROMPT_TEMPLATE.format(
                filepath=filepath, error_text=error_text
            )

            reinforcement = """CRITICAL INSTRUCTION — MUST FOLLOW EXACTLY:
Your response must contain **ONLY** <THOUGHT>...</THOUGHT> (optional) and one or more <EDIT> blocks.
NO explanatory text, NO markdown, NO ```python blocks, NO lists.
If you write anything else the patch will be ignored."""

            messages.append({"role": "user", "content": full_prompt})
            messages.append({"role": "user", "content": reinforcement})

            print("\nAI: \n", end="", flush=True)
            response_text = ""

            # Use try/except to gracefully catch "Connection refused" if Ollama isn't running
            try:
                stream = ollama.chat(
                    model=MODEL, messages=messages, stream=True
                )
                for chunk in stream:
                    content = chunk["message"]["content"]
                    print(content, end="", flush=True)
                    response_text += content
                print()
            except Exception as e:
                err_msg = str(e).lower()
                if "connection refused" in err_msg or "errno 61" in err_msg:
                    print(
                        "\n\n[SYSTEM] ❌ ERROR: Ollama connection refused. Is the Ollama server running?"
                    )
                    print(
                        "   Fix: Open a new terminal and run 'ollama serve', or launch the Ollama desktop app."
                    )
                    # Pop the latest prompts to retry next time
                    messages.pop()
                    messages.pop()
                    continue
                raise e

            messages.append({"role": "assistant", "content": response_text})

            apply_edits(response_text, detected_filepath=filepath)

        except KeyboardInterrupt:
            print("\n[SYSTEM] Interrupted by user.")
            break
        except Exception as e:
            print(f"\n[ERROR] {e}")

        print("\nPress Enter for next fix, or type 'exit' + Enter to quit.")
        if input("> ").strip().lower() in ["exit", "quit"]:
            break


if __name__ == "__main__":
    main()
