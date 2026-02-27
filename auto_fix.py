"""Auto Scan & Fix - Unified Orchestrator for Ruff and Mypy"""

import argparse
import ast
import os
import re
import subprocess
import sys
import time

import ollama

MODEL = "qwen2.5-coder:14b"
MEMORY_FILE = "MEMORY.md"

SYSTEM_PROMPT = """You are an expert Python Mypy type-hint fixer.
You MUST respond EXCLUSIVELY with:
- Optional single <THOUGHT>one short sentence</THOUGHT>
- One or more <EDIT> blocks

CRITICAL RULES - VIOLATION WILL CAUSE PATCH FAILURE:
- NEVER output any text, explanations, or markdown outside the XML tags.
- NEVER include ```python, ```, or ANY markdown code fences in <SEARCH> or <REPLACE>.
- <SEARCH> must be EXACT verbatim raw code copied from the "Full Function Context" or "Surrounding Context" sections in MEMORY.md (these sections contain raw code with NO fences).
- Match every space, tab, blank line, and indentation exactly.
- ALWAYS include 1-2 lines BEFORE and AFTER the changed section in <SEARCH> when possible.
- <REPLACE> must keep the EXACT SAME indentation level as the original.
- A single <EDIT> block MUST represent a CONTINUOUS, CONTIGUOUS block of lines.
- NEVER use `...` to skip lines.
- If changes are needed in multiple locations, use MULTIPLE SEPARATE <EDIT> blocks.
TOP-OF-FILE IMPORT RULE:
- If you need to add typing imports, use TWO separate <EDIT> blocks.
CRITICAL FOCUS RULE:
- Fix ONLY the EXACT Mypy error reported in "Error to fix:".
SPECIAL CASE:
- For "Statement is unreachable [unreachable]": DELETE the unreachable block completely.
GOAL:
Apply the smallest possible surgical fix.
"""

USER_PROMPT_TEMPLATE = """Fix ONLY the Mypy error shown below in the file {filepath}.
Respond EXCLUSIVELY with <THOUGHT> and <EDIT> blocks. NO OTHER TEXT.

Error to fix:
{error_text}

{anchoring_hint}

<EDIT path="{filepath}">
<SEARCH>
exact verbatim raw code (NO ```python fences) from MEMORY.md Full Function Context or Surrounding Context
</SEARCH>
<REPLACE>
fixed raw code (same indentation, no fences)
</REPLACE>
</EDIT>
"""


def parse_args() -> None:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Auto Scan & Fix")
    parser.add_argument("--exclude", "-e", action="append", default=[])
    return parser.parse_args()


def find_containing_function(filepath: str, target_line: int) -> str:
    """Find the source code of the function containing the given line in a file."""
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)

        class FunctionFinder(ast.NodeVisitor):
            def __init__(self):
                self.function_source = ""

            def visit_FunctionDef(self, node):
                end = getattr(node, "end_lineno", node.lineno + 80)
                if node.lineno <= target_line <= end:
                    lines = source.splitlines(keepends=True)
                    self.function_source = "".join(
                        lines[node.lineno - 1 : end]
                    )
                    return
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node):
                self.visit_FunctionDef(node)

        finder = FunctionFinder()
        finder.visit(tree)
        return finder.function_source
    except Exception:
        return ""


def extract_top_imports(lines: list[str]) -> str:
    """Extract the top-level imports from a list of lines."""
    for i, line in enumerate(lines[:60]):
        s = line.strip()
        if s and not s.startswith(("import ", "from ", "#", '"""', "'''")):
            return "".join(lines[: max(i + 12, 30)])
    return "".join(lines[:40])


def extract_snippet(
    filepath: str, error_text: str, context_window: int = 15
) -> tuple[str, str, str, str]:
    """Extract the code snippet pertaining to the error."""
    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[SYSTEM] ❌ Could not read {filepath}: {e}")
        return "", "", "", ""

    pattern = re.compile(r":(\d+)", re.IGNORECASE)
    found = [
        int(m.group(1)) for m in pattern.finditer(error_text) if m.group(1)
    ]
    if not found:
        return extract_top_imports(lines), "", "".join(lines[:250]), ""

    primary_line = found[0]
    full_function = find_containing_function(filepath, primary_line)
    top_imports = extract_top_imports(lines)

    start_idx = max(0, primary_line - 1 - context_window)
    end_idx = min(len(lines), primary_line + context_window + 30)
    surrounding = "".join(lines[start_idx:end_idx])

    print(
        f"[SYSTEM] ✂️ Extracted top imports + full function + context around line {primary_line}"
    )
    target_text = (
        lines[primary_line - 1].strip()
        if primary_line - 1 < len(lines)
        else ""
    )
    return top_imports, full_function, surrounding, target_text


def update_memory_file(
    filepath: str,
    top_imports: str,
    full_function: str,
    surrounding_context: str,
    error_text: str,
) -> bool:
    """Write clean RAW code (NO markdown fences) to MEMORY.md so LLM never copies ```python."""
    try:
        print(
            f"[SYSTEM] + Writing snippet for '{filepath}' to {MEMORY_FILE}..."
        )
        content = "# AI Memory Store - RAW CODE ONLY (copy exactly, no fences)\n\n---\n\n"

        if top_imports.strip():
            content += f"## Top Imports: {filepath}\n{top_imports}\n\n"

        if full_function.strip():
            content += (
                f"## Full Function Context: {filepath}\n{full_function}\n\n"
            )

        content += f"## Error to Fix\n{error_text}\n\n"
        content += f"## Surrounding Context\n{surrounding_context}\n"

        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"[SYSTEM] ❌ Failed to write memory: {e}")
        return False


def flexible_replace(content: str, search_text: str, replace_text: str):
    """Replace content of lines with accuracy."""
    if search_text in content:
        return content.replace(search_text, replace_text, 1)
    return None


def apply_edits(response_text, detected_filepath=None):
    """Apply edits to the file path related to the error."""
    pattern = re.compile(
        r'<EDIT path="(.*?)">.*?<SEARCH>(.*?)</SEARCH>.*?<REPLACE>(.*?)</REPLACE>',
        re.DOTALL,
    )
    matches = pattern.finditer(response_text)
    edits_made = 0
    backups = {}
    for m in matches:
        filepath = m.group(1).strip()
        search_t = m.group(2)
        replace_t = m.group(3)
        if not os.path.exists(filepath):
            continue
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
            new_content = flexible_replace(content, search_t, replace_t)
            if new_content and new_content != content:
                if filepath not in backups:
                    backups[filepath] = content
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"[SYSTEM] ✅ Patched {filepath}")
                edits_made += 1
        except Exception as e:
            print(f"[SYSTEM] ⚠️ Edit failed for {filepath}: {e}")
    return edits_made, backups


def format_bandwidth(total_bytes: int) -> str:
    """Run bandwidth tracker."""
    if total_bytes < 1024:
        return f"{total_bytes} B"
    if total_bytes < 1024 * 1024:
        return f"{total_bytes / 1024:.2f} KB"
    return f"{total_bytes / (1024 * 1024):.2f} MB"


def run_ruff_checks(excludes: list[str] | None = None) -> bool:
    """Run ruff format and check, ignore excluded files/dirs."""
    try:
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "ruff", "format", "."],
            check=False,
            capture_output=True,
        )
        cmd = [sys.executable, "-m", "ruff", "check", "."]
        for e in excludes or []:
            cmd += ["--exclude", str(os.path.abspath(e))]
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
        return r.returncode == 0
    except Exception:
        return False


def get_next_mypy_error(excludes: list[str] | None = None):
    """Run Mypy check, ignore excluded files/dirs, and return ONLY the FIRST error line."""
    print("[SYSTEM] 🔍 Running 'mypy' checks ...")
    cmd = [sys.executable, "-m", "mypy", "src"]
    for e in excludes or []:
        cmd += ["--exclude", str(os.path.abspath(e))]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if r.returncode == 0:
        return None, None
    out = (r.stdout or "").strip()
    if not out:
        return None, None
    first_error_line = out.splitlines()[0].strip()
    filepath = first_error_line.split(":")[0].strip()
    return filepath, first_error_line


def load_memory(p: str) -> str | None:
    """Load MEMORY.md content if it exists."""
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def main():
    """Unified Orchestrator: Auto-Runs smart_coder.py, then handles Mypy with safety reverts."""
    args = parse_args()
    excludes = args.exclude
    print(f"🚀 Auto Scan & Fix Initialized (Model: {MODEL})")
    print("Workflow: ...")

    consecutive_failures = 0
    last_error_text = ""

    while True:
        try:
            print("\n" + "=" * 70)
            if os.path.exists("smart_coder.py"):
                subprocess.run([sys.executable, "smart_coder.py"], check=False)  # noqa: S603

            if os.path.exists(MEMORY_FILE):
                os.remove(MEMORY_FILE)
                print("[SYSTEM] 🧹 Wiped MEMORY.md")

            if not run_ruff_checks(excludes):
                print("[SYSTEM] ❌ Ruff failed")
                break

            filepath, error_text = get_next_mypy_error(excludes)
            if not filepath or not error_text:
                print("\n🎉 [SYSTEM] ALL CLEAR!")
                break

            if error_text == last_error_text:
                consecutive_failures += 1
            else:
                consecutive_failures = 0
                last_error_text = error_text

            if consecutive_failures >= 3:
                break

            print(f"[SYSTEM] Found Mypy Error:\n> {error_text}\n")

            (
                top_imports,
                full_function,
                surrounding_context,
                target_line_text,
            ) = extract_snippet(filepath, error_text)

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]

            if update_memory_file(
                filepath,
                top_imports,
                full_function,
                surrounding_context,
                error_text,
            ) and (mem := load_memory(MEMORY_FILE)):
                messages.append(
                    {"role": "system", "content": f"Memory:\n{mem}"}
                )

            anchoring_hint = (
                f"Hint: error around `{target_line_text}`"
                if target_line_text
                else ""
            )

            full_prompt = USER_PROMPT_TEMPLATE.format(
                filepath=filepath,
                error_text=error_text,
                anchoring_hint=anchoring_hint,
            )

            messages.append({"role": "user", "content": full_prompt})
            messages.append(
                {
                    "role": "user",
                    "content": "Use the Full Function Context when possible. NEVER include ``` in any block.",
                }
            )

            print("AI: ", end="", flush=True)
            response_text = ""
            try:
                for chunk in ollama.chat(
                    model=MODEL, messages=messages, stream=True
                ):
                    c = chunk.get("message", {}).get("content", "")
                    print(c, end="", flush=True)
                    response_text += c
            except Exception as e:
                print(f"\n[OLLAMA] {e}")
                break

            edits_made, backups = apply_edits(response_text, filepath)

            if edits_made > 0:
                print("\n[SYSTEM] Verifying...")
                if not run_ruff_checks(excludes):
                    print("[SYSTEM] Reverting bad edit...")
                    for p, c in backups.items():
                        with open(p, "w", encoding="utf-8") as f:
                            f.write(c)
                else:
                    print("[SYSTEM] ✅ Good fix")
                    time.sleep(3)
            else:
                time.sleep(2)

        except KeyboardInterrupt:
            print("\n[SYSTEM] Interrupted by user.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
