"""Fast Coder Module"""

import os
import re
import sys
import time

import ollama

MODEL = "qwen2.5-coder:7b-instruct"
MEMORY_FILE = "MEMORY.md"

MEMORY_FILE_BLOCK_PATTERN = re.compile(
    r"## File Contents: (.*?)\n```python\n(.*?)\n```\n", re.DOTALL
)

FILEPATH_FROM_ERROR_PATTERN = re.compile(
    r"(?:-->\s*|\A\s*)(\S+?\.py)(?::\d+:\d+)?", re.MULTILINE
)

# Stronger template — forces exact indentation and more context
SYSTEM_PROMPT = """Fix ONLY the Ruff / mypy error(s) shown below in the file {filepath}

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
- ALWAYS include 1-2 lines BEFORE and AFTER the changed line in <SEARCH> to preserve correct indentation
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
            f"[SYSTEM] 🔄 Updating content for '{filepath}' in {MEMORY_FILE}..."
        )
        memory_md_content = existing_block_pattern.sub(
            lambda m: new_file_block, memory_md_content, count=1
        )
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            f.write(memory_md_content)
        return True

    print(f"[SYSTEM] + Adding '{filepath}' to {MEMORY_FILE}...")
    if not memory_md_content.strip():
        memory_md_content = (
            "# AI Memory Store\n\n"
            "This file contains additional context for the AI to reference when performing tasks.\n"
            "It is automatically loaded into the AI's memory at startup.\n\n---\n\n"
        )
    else:
        memory_md_content += "\n---\n\n"

    memory_md_content += new_file_block
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(memory_md_content)
    return True


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
        search_text = match.group(2).strip("\n")  # keep original whitespace
        replace_text = match.group(3).strip("\n")

        if not os.path.exists(filepath):
            print(f"\n[SYSTEM] ❌ Error: Could not find file at {filepath}")
            continue

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            if search_text in content:
                content = content.replace(search_text, replace_text, 1)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"\n[SYSTEM] ✅ Successfully patched: {filepath}")
                edits_made += 1
            else:
                print(
                    f"\n[SYSTEM] ⚠️ Could not find exact <SEARCH> block in {filepath}."
                )
                print("   Likely indentation/context mismatch.")
                print(
                    f"   Provided <SEARCH> (first 300 chars):\n---\n{search_text[:300]}...\n---"
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
            print(
                "   No changes applied. The model ignored the mandatory format."
            )
        else:
            print("\n[SYSTEM] ⚠️ No <EDIT> blocks found. No changes applied.")

    python_blocks = re.findall(
        r"```python\n(.*?)\n```", response_text, re.DOTALL
    )
    if (
        not found_any_edit_block
        and len(python_blocks) == 1
        and "path=" not in response_text
    ):
        print(
            "[SYSTEM] ⚠️ AI used plain code block. Treating as full file replacement (risky)."
        )
        for line in response_text.splitlines():
            if line.strip().startswith("<EDIT path=") or "path=" in line:
                break
        else:
            if detected_filepath:
                print(f"    Applying to {detected_filepath} …")
                try:
                    with open(detected_filepath, "w", encoding="utf-8") as f:
                        f.write(python_blocks[0].strip())
                    print("[SYSTEM] ✅ Applied full replacement")
                    return edits_made + 1
                except Exception as e:
                    print(f"[SYSTEM] Failed full replace: {e}")

    return edits_made


def main():
    """Run script to edit files according to AI response."""
    print(
        f"🚀 Barebones Coder (Smart Linter Mode) Initialized (Model: {MODEL})"
    )
    print(
        "Guided mode: enter file path → paste error → auto-builds perfect prompt.\n"
    )

    initial_memory_content = load_memory(MEMORY_FILE)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if initial_memory_content:
        print(f"[SYSTEM] 🧠 Loaded memory from '{MEMORY_FILE}' into context.")
        messages.insert(
            0,
            {
                "role": "system",
                "content": f"Memory loaded:\n\n{initial_memory_content}",
            },
        )
    else:
        print(f"[SYSTEM] 🧠 No memory file '{MEMORY_FILE}' found or empty.")

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

            # Update memory
            with open(filepath, encoding="utf-8") as f:
                file_content = f.read()
            if update_memory_file(filepath, file_content):
                print(f"[SYSTEM] Memory updated for {filepath}. Reloading...")
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
                time.sleep(1.5)

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

            # Build full prompt
            full_prompt = SYSTEM_PROMPT.format(
                filepath=filepath, error_text=error_text
            )

            # Reinforcement
            reinforcement = """CRITICAL INSTRUCTION — MUST FOLLOW EXACTLY:
Your response must contain **ONLY** <THOUGHT>...</THOUGHT> (optional) and one or more <EDIT> blocks.
NO explanatory text, NO markdown, NO ```python blocks, NO lists.
If you write anything else the patch will be ignored."""

            messages.append({"role": "user", "content": full_prompt})
            messages.append({"role": "user", "content": reinforcement})

            print("\nAI: \n", end="", flush=True)
            response_text = ""
            stream = ollama.chat(model=MODEL, messages=messages, stream=True)
            for chunk in stream:
                content = chunk["message"]["content"]
                print(content, end="", flush=True)
                response_text += content
            print()

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
