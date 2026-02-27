# ⚡️ Smart Coder (`smart_coder.py`)

**Smart Coder** is the guided, user-friendly evolution of Fast Coder.  
It removes almost all manual typing by walking you through two simple steps:

1. Enter the full path to the file you want to fix  
2. Paste the Ruff / mypy / lint error  

The script then **automatically** builds the perfect structured prompt, updates `MEMORY.md`, and sends it to the model. This dramatically increases the chance that the model outputs valid `<EDIT>` blocks.

No more copying long boilerplate prompts every time.

---

## Why Smart Coder?

- **Guided workflow** — no more remembering complex prompt templates
- **Automatic MEMORY.md updates** — always gives the model the exact current file
- **Higher success rate** — the built-in prompt forces correct `<SEARCH>` / `<REPLACE>` format
- **Still zero UI bloat** — runs in the terminal, perfect for Intel Macs and low-RAM machines

---

## Setup

1. Make sure Ollama is running
2. Install the Python client:
   ```bash
   pip install ollama
   ```
3. Pull the recommended model (best format obedience on Intel Macs):
   ```bash
   ollama pull qwen2.5-coder:7b-instruct
   ```
4. (Optional but recommended) Place a `MEMORY.md` file in the same folder — the script will keep it updated automatically.

---

## How to Use (Guided Mode)

Run the script:

```bash
python smart_coder.py
```

You will see:

```
============================================================
Enter the FULL path to the Python file to fix
Press Ctrl+D on a blank line when done.
> 
```

1. Paste the **full absolute path** (e.g. `/Volumes/XTRA/AxiomEngine/src/crucible.py`) and press **Ctrl+D**
2. The script validates the file, reads its current content, and updates `MEMORY.md`
3. Next prompt appears:

```
Paste the FULL error / lint output to fix (multi-line OK)
Press Ctrl+D on a blank line when finished.
> 
```

4. Paste the entire error message (including the `-->`, line numbers, help text, etc.) and press **Ctrl+D**
5. The AI streams its response → edits are automatically applied → you get success/failure feedback
6. Press Enter for the next fix, or type `exit` to quit

---

## What Happens Behind the Scenes

- The script builds a **very strict prompt** that includes:
  - Exact file path
  - Your pasted error
  - Clear instructions to use verbatim `<SEARCH>` from MEMORY.md
  - Requirement to include surrounding lines for correct indentation
- A reinforcement message is added to further enforce format obedience
- Memory is refreshed before every fix so the model always sees the latest file content

---

## Example Full Run

```
Enter the FULL path to the Python file to fix
> /Volumes/XTRA/AxiomEngine/src/crucible.py
[SYSTEM] Using file: /Volumes/XTRA/AxiomEngine/src/crucible.py
[SYSTEM] Memory updated for /Volumes/XTRA/AxiomEngine/src/crucible.py. Reloading...

Paste the FULL error / lint output to fix
> SIM108 Use ternary operator ... (paste entire error)
^D

AI: 
<THOUGHT>
SIM108: Use ternary operator instead of if-else block
</THOUGHT>
<EDIT path="/Volumes/XTRA/AxiomEngine/src/crucible.py">
<SEARCH>
        score = max(0.0, min(1.0, score))

        if score >= 0.8 or score >= 0.5:
            state = "suspected_fragment"
        else:
            state = "unknown"
</SEARCH>
<REPLACE>
        score = max(0.0, min(1.0, score))

        state = "suspected_fragment" if score >= 0.8 or score >= 0.5 else "unknown"
</REPLACE>
</EDIT>

[SYSTEM] ✅ Successfully patched: /Volumes/XTRA/AxiomEngine/src/crucible.py
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Could not find exact <SEARCH> block" | The model used wrong indentation. Try again — the stronger template usually fixes it on the second try. |
| No <EDIT> blocks at all | Switch to `qwen2.5-coder:7b-instruct` (or 14b-instruct) if you're on a larger model. |
| File not found | Use the **full absolute path** (`/Volumes/...` on macOS). |
| Memory not updating | Make sure the path you enter actually exists and is a `.py` file. |

---

## Tips for Best Results

- Always use the **full absolute path** (helps memory update and `<EDIT>` tag accuracy)
- Paste the **entire** lint error (including the `help:` line)
- The model works best with `qwen2.5-coder:7b-instruct`
- If you ever want to go back to free-form mode, just tell me and I can give you that version again

---

**Happy fast coding!**  
You should now be able to blaze through hundreds of lint fixes per hour with almost zero manual effort.

Created for the guided version of Smart Coder (February 2026)