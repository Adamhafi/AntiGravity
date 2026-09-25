"""Install shared memory integration for Antigravity 2.0 and Antigravity IDE."""
import argparse
import json
from pathlib import Path
import sys


SOURCE = Path(__file__).resolve().parent
SUPPORTED_SURFACES = ["Antigravity 2.0 (standalone)", "Antigravity IDE"]


def plan(home):
    home = Path(home).expanduser().resolve()
    skill = home / ".gemini/config/skills/persistent-memory"
    store = home / ".gemini/antigravity-ide/user-memory"
    # Both apps discover the shared config paths. Keep the initial data location
    # for compatibility; the helper does not depend on the IDE application.
    rule = home / ".gemini/config/rules/persistent-memory.md"
    substitutions = {"{{SKILL_DIR}}": skill.as_posix(), "{{MEMORY_DIR}}": store.as_posix()}
    sources = {
        skill / "SKILL.md": SOURCE / "skills/persistent-memory/SKILL.md",
        skill / "scripts/memory.py": SOURCE / "skills/persistent-memory/scripts/memory.py",
        rule: SOURCE / "rules/persistent-memory.md",
    }
    files = {}
    for target, source in sources.items():
        content = source.read_text(encoding="utf-8")
        for key, value in substitutions.items():
            content = content.replace(key, value)
        files[target] = content.encode("utf-8")
    return home, files


def install(home, dry_run=False):
    home, files = plan(home)
    # Check every destination before writing any file. Existing different content
    # requires manual review; never silently replace a local customization.
    for target, content in files.items():
        for part in [target, *target.parents]:
            if part == home:
                break
            if part.is_symlink() or part.is_junction():
                raise ValueError("Refusing a linked install path: " + str(part))
        if target.exists() and (not target.is_file() or target.read_bytes() != content):
            raise ValueError("Existing file differs; preserved unchanged: " + str(target))
    created = []
    try:
        if not dry_run:
            for target, content in files.items():
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as f:
                    created.append(target)
                    f.write(content)
    except OSError:
        # Undo only files this invocation created, never existing files or directories.
        for target in reversed(created):
            target.unlink()
        raise
    return {"dry_run": dry_run, "created": [str(p) for p in created],
            "files": [str(p) for p in files], "memories_imported": False,
            "supported_surfaces": SUPPORTED_SURFACES,
            "memory_store": str(home / ".gemini/antigravity-ide/user-memory"),
            "activation": "Verify visible skill/helper use in a fresh conversation in each app; file checks alone do not verify runtime activation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home(), help="Alternate home for isolated tests/staging")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required")
    try:
        print(json.dumps(install(args.home, args.dry_run), indent=2))
        return 0
    except (OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
