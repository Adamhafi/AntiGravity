# AntiGravity Persistent Memory

A lightweight, local memory layer for **Antigravity 2.0 (the regular standalone app) and Antigravity IDE**. It helps the agent recall project decisions, confirmed fixes, user preferences, and unfinished work across conversations and across both apps.

**File-based memory, not model training.** This package does not change your model, persona, permissions, or existing rules. It does not claim to make Antigravity universally better than another coding agent.

## Features

- **Recall from any chat:** ask about a named past project without reopening its workspace. A lightweight project directory finds its saved notes by name, path, or alias.
- **Separate project storage:** each resolved workspace path has its own memory namespace. Clones and worktrees remain separate, but you can intentionally recall any of them.
- **Remember how you worked:** milestone summaries capture your approach, constraints, decisions and reasons, verified changes, and stopping point. The agent is instructed to save these during opted-in work without a separate "remember this" prompt.
- **Shared preferences:** only explicitly stated user preferences belong in shared memory.
- **Source-backed notes:** readable Markdown with sources, timestamps, verification status, tags, and revision numbers.
- **Selective recall:** keyword search returns bounded excerpts and paths, rather than loading every note.
- **Revision history:** previous versions are preserved; stale updates are rejected; identical saves are no-ops.
- **Forget support:** delete a selected note and its local revision history on request.
- **Conservative installation:** no overwrite of differing files, no imported personal memories, no account changes, and no background service.
- **Standard library only:** no Python packages, database, embedding service, or API key needed.

## Requirements

- Antigravity 2.0 (standalone), Antigravity IDE, or both, with global rules and skills support.
- Python **3.12 or newer**, available as `python` (or substitute your interpreter command).
- Git to clone this repository, or download and extract its ZIP.

The helper and installer have been tested locally on Windows with Python 3.13. Other platforms have not yet been validated here.

## App compatibility

| App | Skill location | Rule location | Status |
| --- | --- | --- | --- |
| Antigravity 2.0, regular standalone app | `~/.gemini/config/skills/` | `~/.gemini/config/rules/` | Uses the documented shared locations; fresh-session activation needs an in-app check |
| Antigravity IDE | `~/.gemini/config/skills/` | `~/.gemini/config/rules/` | Uses the documented shared locations; fresh-session activation needs an in-app check |

**Install once for both.** No separate IDE installation is required to use the package from standalone Antigravity. Both apps must run under the same account to use the same memory store. Save using a consistent project root; later conversations can find that project by name even outside its folder. A different clone or worktree intentionally has a separate namespace.

The memory directory retains the initial name `~/.gemini/antigravity-ide/user-memory` to avoid splitting or relocating existing notes. It is an ordinary directory used by the Python helper, not an IDE API dependency. The installer does not enable unrestricted filesystem access; resolve any denied memory-path access narrowly in the affected app.

The dedicated `agy` CLI has different documented global skill locations and is **not installed/configured by this package**. "Regular app" here means the Antigravity 2.0 desktop application, not that CLI.

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

1. Open a fresh conversation in a project and check that `persistent-memory` appears in Customizations. In standalone Antigravity, use the application menu or project settings. In Antigravity IDE, use the agent side panel's **... > Customizations** menu. If missing, finish ongoing work before reloading the application.
2. Ask: **"Remember this project-only test note: the smoke-test label is cedar-orbit-47. Use note ID memory-smoke-test, mark it user-confirmed, and do not modify source code. Show the saved memory path."**
3. Open another fresh conversation in the same project and ask: **"What smoke-test label did I ask you to remember? Retrieve it from persistent memory and show the source file."**
4. Check visible tool activity for the actual saved-note read. If automatic selection fails, explicitly ask it to read the installed `persistent-memory/SKILL.md`. Explicit invocation and automatic selection are different checks.
5. In a different project, ordinary current-project recall should not load the first project's notes. Explicitly ask about the first project **by name**, and its stored note should be discoverable through `projects --query`, then `recall --project-id`.
6. Clean up in the original project: **"Forget memory-smoke-test and its local revision history. Do not modify source code."**

For a cross-app check, save the test note in standalone Antigravity, then perform step 3 in Antigravity IDE with the **same project folder**, or vice versa. Verify the visible read of the same note file. Python tests exercise the shared storage, not either application's model-driven activation.

Use the same actual project root across conversations. If Antigravity denies a path or command, resolve only that access issue rather than disabling permissions globally.

## Remember Project X from a new chat

The intended experience is:

1. Work on Project X. Before finishing a meaningful milestone, the agent updates `project-overview` and any useful task-specific lessons or handoffs.
2. Start a new IDE chat, in the same project, a different project, or without that old checkout open.
3. Ask: **"What did we do on Project X, how did we approach it, and where did we stop?"**
4. The agent searches the saved project directory, selects X, reads its relevant notes, and answers with sources and any outstanding uncertainty.

You do not need to repeat the old chat or give the helper command. A first saved note automatically makes its folder name discoverable. For a friendlier project name, use `register` once. Existing memory manifests remain compatible without importing or rewriting their notes. If multiple projects have the same name, the agent must disambiguate rather than mix them.

This remembers **saved summaries**, not every conversation verbatim. Automatic writing and retrieval still depend on the IDE agent following its rule. A closed/crashed conversation with no saved milestone has no recoverable memory through this package. Older unsaved chats are not automatically imported.

## Everyday prompts

- "Remember this project decision and why we made it."
- "Continue from the saved handoff, checking it against the current files."
- "What caused the previous build failure, and what fix was verified?"
- "What did we decide on Project X, and where did we stop?"
- "How did I approach testing in the Client Portal project?"
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

# Discover another remembered project without changing the current workspace.
python $memory projects --query 'Project X'
# Replace ID_FROM_PROJECTS with the selected result's actual project_id.
python $memory recall --project-id 'ID_FROM_PROJECTS'
python $memory show --project-id 'ID_FROM_PROJECTS' --id 'project-overview'

# Optional friendly name; this does not merge or move the project's notes.
python $memory register --project $project --name 'Project X' --alias 'Client Portal'

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

Tests use temporary directories, not your live memory store. They cover project isolation, shared preferences, cross-project discovery and explicit recall, aliases, ambiguous names, missing checkouts, revision checks, history, duplicate saves, keyword recall, malformed notes, Unicode, representative secret rejection, forget behavior, CLI persistence across processes, path traversal, and installer behavior. A separate-process test finds Project X by name while running from Project Y's directory. Symlink/junction tests depend on the operating system and available privileges.

Fresh-session automatic activation must be tested separately using the in-app procedure above.

## Official integration references

- [Antigravity rules](https://antigravity.google/docs/rules/)
- [Antigravity agent skills](https://www.antigravity.google/docs/skills?tab=ide)

This is an independent customization, not an official Google product.
