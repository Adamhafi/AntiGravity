# AntiGravity Persistent Memory

A lightweight, local memory layer for Google Antigravity. It helps the agent recall project decisions, confirmed fixes, user preferences, and unfinished work across conversations.

**File-based memory, not model training.** This package does not change your model, persona, permissions, or existing rules. It does not claim to make Antigravity universally better than another coding agent.

## Features

- **Project isolation:** each resolved workspace path has its own memory namespace. Clones and worktrees remain separate.
- **Shared preferences:** only explicitly stated user preferences belong in shared memory.
- **Source-backed notes:** readable Markdown with sources, timestamps, verification status, tags, and revision numbers.
- **Selective recall:** keyword search returns bounded excerpts and paths, rather than loading every note.
- **Revision history:** previous versions are preserved; stale updates are rejected; identical saves are no-ops.
- **Forget support:** delete a selected note and its local revision history on request.
- **Conservative installation:** no overwrite of differing files, no imported personal memories, no account changes, and no background service.
- **Standard library only:** no Python packages, database, embedding service, or API key needed.

## Requirements

- Antigravity IDE with global rules and skills support.
- Python **3.12 or newer**, available as `python` (or substitute your interpreter command).
- Git to clone this repository, or download and extract its ZIP.

The helper and installer have been tested locally on Windows with Python 3.13. Other platforms have not yet been validated here.

## Install

```powershell
git clone https://github.com/Adamhafi/AntiGravity.git
cd AntiGravity
python install.py --dry-run
python install.py
```

Running the installer opts into the documented automatic recall and milestone-save instructions. It installs only these three files under **your own home directory**:

```text
~/.gemini/config/
  rules/persistent-memory.md
  skills/persistent-memory/
    SKILL.md
    scripts/memory.py
```

The installer renders the instruction templates with your actual paths. Do not manually copy the unrendered templates into Antigravity. An identical installation is a no-op. If a target file differs, installation stops before writing anything; review and back up your custom files before replacing them manually. The installer is not an automatic upgrade tool.

Actual notes are created on the first save, outside this checkout:

```text
~/.gemini/antigravity-ide/user-memory/
  shared/
    scope.json
    notes/<id>.md
    history/<id>/<revision>.md
  projects/<workspace-path-hash>/
    scope.json
    notes/<id>.md
    history/<id>/<revision>.md
```

No existing persona files, model settings, MCP configuration, or internal Antigravity knowledge files are modified. No restart is forced.

## Verify it in Antigravity

The rule asks the agent to use memory automatically. That is **model-mediated behavior**, not a guaranteed hook. A passing Python test does not prove that an Antigravity conversation loaded the skill.

1. Open a fresh conversation in a project and check that `persistent-memory` appears in Customizations. If missing, finish ongoing work before reloading the application.
2. Ask: **"Remember this project-only test note: the smoke-test label is cedar-orbit-47. Use note ID memory-smoke-test, mark it user-confirmed, and do not modify source code. Show the saved memory path."**
3. Open another fresh conversation in the same project and ask: **"What smoke-test label did I ask you to remember? Retrieve it from persistent memory and show the source file."**
4. Check visible tool activity for the actual saved-note read. If automatic selection fails, explicitly ask it to read the installed `persistent-memory/SKILL.md`. Explicit invocation and automatic selection are different checks.
5. In a different project, the first project's test note should not appear.
6. Clean up in the original project: **"Forget memory-smoke-test and its local revision history. Do not modify source code."**

Use the same actual project root across conversations. If Antigravity denies a path or command, resolve only that access issue rather than disabling permissions globally.

## Everyday prompts

- "Remember this project decision and why we made it."
- "Continue from the saved handoff, checking it against the current files."
- "What caused the previous build failure, and what fix was verified?"
- "Do not remember this conversation."
- "Forget the saved note about X and its local history."

Routine project work should recall relevant notes and save meaningful milestones. Unrelated simple questions should skip memory. The skill asks the agent to avoid saving raw transcripts, speculation, repeated notes, or guessed preferences.

## Use the helper directly

PowerShell, after installation:

```powershell
$memory = Join-Path $HOME '.gemini/config/skills/persistent-memory/scripts/memory.py'
$project = (Get-Location).Path

# Recall is read-only. Omit --query to see recent notes.
python $memory recall --project $project --query 'build tests'
python $memory show --project $project --id 'test-command'

# Read a UTF-8 JSON payload, or use --input - for stdin.
python $memory save --project $project --input 'note.json'

# Use the actual current revision, not a guessed number.
python $memory forget --project $project --id 'test-command' --expected-revision 1
```

Example `note.json` structure, replace the example with your observed facts before saving:

```json
{
  "id": "test-command",
  "kind": "fact",
  "title": "Focused test command",
  "source": "Actual file or completed terminal check, date, and relevant commit",
  "status": "unverified",
  "tags": ["tests"],
  "body": "Describe the actual command, working directory, result, and when it needs rechecking.",
  "expected_revision": 0
}
```

`expected_revision: 0` creates a new note. Updates require the revision returned by `show`. For shared preferences, replace `--project ...` with `--shared` and use `kind: preference`.

| Field | Values |
| --- | --- |
| `kind` | `preference`, `fact`, `decision`, `lesson`, `handoff` |
| `status` | `verified`, `user-confirmed`, `unverified`, `retired` |

`verified` means observed evidence, not confidence. Retired notes remain on disk but are excluded from recall. Old or unverified notes are flagged for rechecking; even recent notes can become stale. Memory is evidence, not authority over current requests or files.

## Privacy and limitations

- Memories are **local plaintext**, not encrypted by this package. Antigravity may send retrieved notes to its configured model as context.
- Never store credentials, cookies, private keys, secret-bearing URLs, raw personal records, or full logs. Pattern checks reject some obvious secrets; they are not a comprehensive secret scanner.
- This repository contains code, templates, and synthetic tests, **not the author's personal memories, configuration snapshots, or conversation history**.
- Search is keyword-based, not semantic. Large stores may eventually need indexing.
- Revision history is local file history, not remote backup. Forgetting a note does not erase external backups or previous conversations.
- Lock files prevent cooperative concurrent writes. After a crash, inspect the lock's PID and timestamp and confirm the writer has stopped before removing that exact stale lock. This is not a security boundary against another process controlling the account.
- No claim is made about improved intelligence, coding quality, quota savings, or latency without separate benchmarks.

## Pause automatic use

For the current conversation, say **"memory off for this conversation."**

To disable the automatic-use rule for future conversations without deleting memories:

```powershell
Rename-Item -LiteralPath (Join-Path $HOME '.gemini/config/rules/persistent-memory.md') -NewName 'persistent-memory.md.disabled'
```

Start a fresh conversation afterward; an existing conversation may retain loaded instructions. The skill is still available for explicit use. To re-enable, rename `persistent-memory.md.disabled` back to `persistent-memory.md`. Do not overwrite an existing destination without inspecting it. To fully remove discovery, also move the installed skill directory outside Antigravity's scanned skills directories. Keep your memory store unless you explicitly intend to delete it.

## Development and tests

From this repository's root:

```powershell
python -m unittest discover -s tests -v
```

Tests use temporary directories, not your live memory store. They cover project isolation, shared preferences, revision checks, history, duplicate saves, keyword recall, malformed notes, Unicode, representative secret rejection, forget behavior, CLI persistence across processes, path traversal, and installer behavior. Symlink/junction tests depend on the operating system and available privileges.

Fresh-session automatic activation must be tested separately using the in-app procedure above.

## Official integration references

- [Antigravity rules](https://antigravity.google/docs/rules/)
- [Antigravity agent skills](https://www.antigravity.google/docs/skills?tab=ide)

This is an independent customization, not an official Google product.
