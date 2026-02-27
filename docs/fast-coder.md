# ⚡️ Fast Coder (`fast_coder.py`)

**Fast Coder** is a minimalist, terminal-only local AI coding assistant optimized for older hardware (Intel Macs, low-RAM machines).  
It lets you fix lint errors (Ruff, mypy, flake8, etc.) by chatting with Ollama models — the AI proposes precise search/replace edits that the script automatically applies to your files.

No heavy UI, no JSON tool calling, no background processes eating CPU/RAM.

## Core Mechanism

The script forces the model to output changes in a strict XML-like format:

```xml
<THOUGHT>Brief reason for this one fix</THOUGHT>
<EDIT path="/full/path/to/file.py">
<SEARCH>
exact original lines (copied from MEMORY.md or disk)
</SEARCH>
<REPLACE>
corrected lines (same indentation!)
</REPLACE>
</EDIT>
```

- The script parses **only** these blocks.
- Anything else (markdown, explanations, ```python blocks, lists) → ignored.
- Multiple fixes → **separate** <EDIT> blocks (one change per block).

## Setup

1. Ollama must be running
2. Install the client:
   ```bash
   pip install ollama
   ```
3. Recommended model for Intel Macs (fast + good format obedience):
   ```bash
   ollama pull qwen2.5-coder:7b-instruct
   ```
   (The 14b-instruct version also works well if you have ≥12 GB RAM)

4. (Optional but **strongly recommended**) Create `MEMORY.md` in the same folder as `fast_coder.py`

## MEMORY.md – How it really works now

The script **automatically updates** `MEMORY.md` when you paste a prompt containing a recognizable file path (e.g. `/Volumes/XTRA/.../crucible.py` or just `src/crucible.py`).

Current behavior:
- If the path appears in your input → script reads the **actual file from disk** right now
- Updates / adds the block `## File Contents: /full/path/to/file.py` with current disk content
- Reloads the updated memory into the conversation
- Gives the model a 2-second pause before querying Ollama

So you **usually do not need to manually maintain MEMORY.md** anymore — just make sure the file path is in your prompt.

## Exact Workflow

1. Run the script
   ```bash
   python fast_coder.py
   ```

2. When you see:
   ```
   You (Press Ctrl+D to submit):
   ```
   paste your error/lint message + file path.

3. **Important:**
   - Include the **absolute path** somewhere in the prompt (helps memory update & <EDIT> tag)
   - **Do NOT** paste large code blocks — the model should use MEMORY.md instead
   - Press **Ctrl+D** (not Enter) to send the multi-line input

4. The model streams → script parses <EDIT> blocks → applies changes → prints success or failure

## Best Prompt Template (copy-paste & adapt)

```text
Fix ONLY the Ruff / mypy error(s) shown below in the file /Volumes/XTRA/AxiomEngine/src/crucible.py

Respond **EXCLUSIVELY** with:
- Zero or one <THOUGHT>single short sentence describing the rule being fixed</THOUGHT>
- One or more complete <EDIT> blocks in this exact nested format — nothing else

<EDIT path="/full/path/to/file.py">
<SEARCH>
exact original lines from memory, with correct indentation and whitespace
</SEARCH>
<REPLACE>
fixed lines, keeping the exact same indentation level
</REPLACE>
</EDIT>

Rules you **must** follow:
- One <EDIT> block per atomic change
- <SEARCH> must be verbatim from MEMORY.md (or the file on disk)
- Keep indentation **identical** in <SEARCH> and <REPLACE>
- Docstrings: use **imperative mood** (Clean up…, Generate…, Check…)
- No explanations, no markdown, no lists, no ```python

The script ignores your entire response if format is wrong.

Error to fix:
D401 First line of docstring should be in imperative mood: "Basic cleanup before NLP processing."
   --> src/crucible.py:123:5
    |
122 | def _sanitize_text(text):
123 |     """Basic cleanup before NLP processing."""
    |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
124 |     if not text:
125 |         return ""
    |

Use exact path in <EDIT> tag: /Volumes/XTRA/AxiomEngine/src/crucible.py
```

## Common Failure Modes & Fixes

| Symptom                                      | Likely Cause                                      | Solution                                                                 |
|----------------------------------------------|---------------------------------------------------|--------------------------------------------------------------------------|
| `[SYSTEM] ⚠️ No <EDIT> blocks found`        | Model ignored format, wrote markdown or plain code | Use stronger prompt above + qwen2.5-coder:7b-instruct                   |
| `Could not find exact <SEARCH> block`        | Indentation mismatch or wrong context lines       | Make sure path is in prompt → memory updates → model sees real file     |
| No memory update happens                     | No recognizable `.py` path in your input          | Always include full/absolute path in prompt                              |
| Model puts code directly in <EDIT> without <SEARCH>/<REPLACE> | Model hallucinated custom format                  | Switch to 7b-instruct model or add even stricter prompt reminders       |
| Changes applied but wrong place              | Model used wrong context in <SEARCH>              | Paste more precise snippet or rely on auto-updated MEMORY.md            |

## Tips for Best Results

- Use **qwen2.5-coder:7b-instruct** — it follows rigid tagged formats much better than most 30b+ models
- Always include the full path early in the prompt
- If the model still writes explanations → add one more line at the end:
  ```
  Output format violation = no patch applied. Use <EDIT> only.
  ```
- After patching → immediately run Ruff/mypy again and paste the next error

Happy fast coding!