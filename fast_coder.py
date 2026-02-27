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

SYSTEM_PROMPT = """\
OUTPUT FORMAT IS MANDATORY — ANY DEVIATION = RESPONSE IGNORED

Allowed content ONLY:
• Optional <THOUGHT>explanation of one issue</THOUGHT>
• One or more complete <EDIT path="…"> blocks

FORBIDDEN:
- Any text outside those tags
- ```python or any code blocks
- Lists, summaries, "Here is the fix", "### Changes"
- Combining fixes into one block

Rules (must obey):
- One <EDIT> per atomic change
- <SEARCH> = exact lines from MEMORY (indent/whitespace preserved)
- <REPLACE> = modified version, same indent
- Max 3 lines in <SEARCH> unless necessary
- Docstrings: imperative mood

Example ONLY structure:

<THOUGHT>RET504: unnecessary assignment before return</THOUGHT>
<EDIT path="/path/file.py">
<SEARCH>
    x = compute()
    return x
</SEARCH>
<REPLACE>
    return compute()
</REPLACE>
</EDIT>

You MUST use only the above format. No exceptions.
Use MEMORY as exact source for <SEARCH>.
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

    # Adding new file
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


def extract_filepath_from_input(user_input: str) -> str | None:
    """Extract a Python filepath from the user's input."""
    match = FILEPATH_FROM_ERROR_PATTERN.search(user_input)
    if match:
        detected_path = match.group(1)
        if not os.path.isabs(detected_path):
            return os.path.abspath(detected_path)
        return detected_path
    return None


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
        search_text = match.group(2).strip("\n")
        replace_text = match.group(3).strip("\n")

        if not os.path.exists(filepath):
            print(f"\n[SYSTEM] ❌ Error: Could not find file at {filepath}")
            continue

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            if search_text in content:
                content = content.replace(
                    search_text, replace_text, 1
                )  # only first occurrence
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"\n[SYSTEM] ✅ Successfully patched: {filepath}")
                edits_made += 1
            else:
                print(
                    f"\n[SYSTEM] ⚠️ Could not find exact <SEARCH> block in {filepath}."
                )
                print("   Likely indentation/context mismatch.")
                print(f"   Provided <SEARCH>:\n---\n{search_text}\n---")
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
            print(
                "   Try re-prompting or switching to a more format-compliant model."
            )
        else:
            print("\n[SYSTEM] ⚠️ No <EDIT> blocks found. No changes applied.")
            print("   AI did not propose any valid edits.")

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
        "Paste your error snippet(s). DO NOT paste any additional code. "
        "Press Ctrl+D to submit. Type 'exit' and press Ctrl+D to quit.\n"
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
        print(
            f"[SYSTEM] 🧠 No memory file '{MEMORY_FILE}' found or it's empty. "
            "AI will operate with limited context."
        )

    while True:
        try:
            print("\nYou (Press Ctrl+D to submit): ")
            user_input = sys.stdin.read().strip()

            if not user_input:
                break
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input:
                continue

            detected_filepath = extract_filepath_from_input(user_input)
            if detected_filepath:
                if os.path.exists(detected_filepath):
                    print(
                        f"[SYSTEM] Detected file path: '{detected_filepath}' from input."
                    )
                    with open(detected_filepath, encoding="utf-8") as f:
                        file_content_on_disk = f.read()
                    memory_was_updated = update_memory_file(
                        detected_filepath, file_content_on_disk
                    )
                    if memory_was_updated:
                        print(
                            f"[SYSTEM] Memory updated for '{detected_filepath}'. "
                            "Reloading memory..."
                        )
                        reloaded_memory_content = load_memory(MEMORY_FILE)
                        if (
                            messages
                            and messages[0]["role"] == "system"
                            and "Memory loaded:" in messages[0]["content"]
                        ):
                            messages.pop(0)
                        messages.insert(
                            0,
                            {
                                "role": "system",
                                "content": f"Memory loaded:\n\n{reloaded_memory_content}",
                            },
                        )
                        print(
                            "[SYSTEM] Pausing 2s for memory update to settle..."
                        )
                        time.sleep(2)
                else:
                    print(
                        f"[SYSTEM] ⚠️ Detected path '{detected_filepath}' does not exist. "
                        "Cannot add to memory."
                    )

            messages.append({"role": "user", "content": user_input})

            if (
                len(messages) > 1
                and messages[-1]["role"] == "user"
                and "CRITICAL INSTRUCTION" in messages[-1]["content"]
            ):
                messages.pop()

            messages.append(
                {
                    "role": "user",
                    "content": """CRITICAL INSTRUCTION — MUST FOLLOW EXACTLY:
Your response must contain **ONLY** <THOUGHT>...</THOUGHT> (optional)
and one or more <EDIT path="...">...</EDIT> blocks.

NO explanatory text, NO markdown, NO ```python blocks, NO lists,
NO summaries outside <THOUGHT>.

If you write anything else the patch script will ignore your entire response.

Apply the requested fix using the exact format shown in the system prompt.""",
                }
            )

            print("\nAI: \n", end="", flush=True)
            response_text = ""
            stream = ollama.chat(model=MODEL, messages=messages, stream=True)
            for chunk in stream:
                content = chunk["message"]["content"]
                print(content, end="", flush=True)
                response_text += content
            print()

            messages.append({"role": "assistant", "content": response_text})

            apply_edits(response_text, detected_filepath)

        except KeyboardInterrupt:
            print("\n[SYSTEM] Interrupted by user.")
            break
        except Exception as e:
            print(f"\n[ERROR] {e}")


if __name__ == "__main__":
    main()
