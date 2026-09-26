"""Local, project-isolated Markdown memory. Python 3.12+, standard library only."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

DEFAULT_ROOT = Path.home() / ".gemini/antigravity-ide/user-memory"
PREFIX = "<!-- memory-meta: "
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
KINDS = {"preference", "fact", "decision", "lesson", "handoff"}
STATES = {"verified", "user-confirmed", "unverified", "retired"}
# Defense in depth, not a comprehensive secret classifier. Review before saving.
SECRETS = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:sk-(?:proj-)?|ghp_|github_pat_)[A-Za-z0-9_-]{20,}|"
    r"\bAKIA[A-Z0-9]{16}\b|"
    r"\bBearer\s+[A-Za-z0-9_.+/=-]{16,}|"
    r"(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[=:]\s*\S+",
    re.I,
)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_path(root: Path, *parts: str) -> Path:
    """Reject links/junctions below the store, including dangling links."""
    root = root.absolute()
    p = root
    for item in [root, *(root / Path(*parts[:i]) for i in range(1, len(parts) + 1))]:
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise ValueError("Memory paths cannot be symbolic links or junctions")
    p = root.joinpath(*parts)
    if not p.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes memory store")
    return p


def slug(value):
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise ValueError("ID must be 1-64 lowercase letters, digits or hyphens")
    return value


def project_metadata(root, project_id):
    if not isinstance(project_id, str) or not re.fullmatch(r"[0-9a-f]{24}", project_id):
        raise ValueError("Invalid project ID; use an ID returned by projects")
    folder = safe_path(root, "projects", project_id)
    manifest = safe_path(root, "projects", project_id, "scope.json")
    if manifest.stat().st_size > 8000:
        raise ValueError("Project metadata too large")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    identity = data.get("identity") if isinstance(data, dict) else None
    if not isinstance(identity, str) or not Path(identity).is_absolute():
        raise ValueError("Invalid project identity")
    if hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24] != project_id:
        raise ValueError("Project identity does not match directory")
    name = data.get("name", Path(identity).name)
    aliases = data.get("aliases", [])
    if not isinstance(name, str) or not name.strip() or len(name) > 160:
        raise ValueError("Invalid project name")
    if not isinstance(aliases, list) or len(aliases) > 12 or any(not isinstance(a, str) or not a.strip() or len(a) > 160 for a in aliases):
        raise ValueError("Invalid project aliases")
    return folder, {"project_id": project_id, "name": name, "aliases": aliases, "identity": identity,
                    "manifest": str(manifest)}


def scope(root, project=None, shared=False, project_id=None):
    if sum((bool(project), bool(shared), bool(project_id))) != 1:
        raise ValueError("Select exactly one project path, saved project ID, or shared scope")
    if shared:
        return safe_path(root, "shared"), "shared"
    if project_id:
        folder, meta = project_metadata(root, project_id)
        return folder, meta["identity"]
    p = Path(project).expanduser().resolve(strict=True)
    if not p.is_dir():
        raise ValueError("Project must be an existing directory")
    identity = os.path.normcase(str(p))
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return safe_path(root, "projects", key), identity


def projects(root, query="", limit=10):
    """Search the project directory without loading any note bodies or history."""
    directory = safe_path(root, "projects")
    terms = set(re.findall(r"\w+", query.casefold()))
    found, errors = [], []
    for child in sorted(directory.glob("*")):
        try:
            folder, meta = project_metadata(root, child.name)
            names = [meta["name"], *meta["aliases"]]
            searchable = " ".join([*names, meta["identity"]]).casefold()
            if terms and not all(term in searchable for term in terms):
                continue
            exact = query.strip().casefold() in [name.casefold() for name in names]
            notes = safe_path(root, "projects", child.name, "notes")
            found.append({**meta, "has_notes": any(notes.glob("*.md")), "exact_name_match": exact})
        except (ValueError, OSError, TypeError, KeyError):
            errors.append({"path": str(child), "error": "Invalid or inaccessible project metadata"})
    found.sort(key=lambda p: (not p["exact_name_match"], p["name"].casefold(), p["identity"]))
    return {"projects": found[:limit], "total_matches": len(found), "requires_selection": len(found) > 1,
            "errors": errors, "note": "Select the intended project ID before recall. Project boundaries remain separate."}


def register(root, project, name, aliases=None):
    """Give a project a user-recognizable name without changing its note namespace."""
    labels = [name, *(aliases or [])]
    if len(labels) > 13 or any(not isinstance(s, str) or not s.strip() or len(s) > 160 for s in labels):
        raise ValueError("Use a nonempty name and at most 12 short aliases")
    if SECRETS.search(" ".join(labels)):
        raise ValueError("Possible secret detected in project label")
    folder, identity = scope(root, project)
    p = safe_path(root, *folder.relative_to(root.absolute()).parts, "scope.json")
    with locked(folder):
        old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"identity": identity}
        if old.get("identity") != identity:
            raise ValueError("Scope identity mismatch")
        data = {"identity": identity, "name": name.strip(),
                "aliases": list(dict.fromkeys(s.strip() for s in (aliases if aliases is not None else old.get("aliases", []))))}
        if data != old:
            atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        return {"project_id": folder.name, "changed": data != old, **data}


def read_note(path):
    if path.stat().st_size > 24_000:
        raise ValueError("Memory note too large")
    raw = path.read_text(encoding="utf-8")
    head, sep, body = raw.partition("\n")
    if not sep or not head.startswith(PREFIX) or not head.endswith(" -->"):
        raise ValueError("Invalid memory metadata")
    meta = json.loads(head[len(PREFIX):-4])
    for field in ("id", "kind", "title", "source", "status", "tags", "created", "updated", "revision"):
        if field not in meta:
            raise ValueError("Incomplete memory metadata")
    if meta["id"] != path.stem or not SLUG.fullmatch(meta["id"]):
        raise ValueError("Memory ID does not match filename")
    if meta["kind"] not in KINDS or meta["status"] not in STATES:
        raise ValueError("Invalid memory kind/status")
    if not isinstance(meta["revision"], int) or meta["revision"] < 1:
        raise ValueError("Invalid memory revision")
    if not all(isinstance(meta[k], str) for k in ("title", "source", "created", "updated")):
        raise ValueError("Invalid text metadata")
    if not isinstance(meta["tags"], list) or not all(isinstance(t, str) for t in meta["tags"]):
        raise ValueError("Invalid tags")
    dt = datetime.fromisoformat(meta["updated"])
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return meta, body.strip()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def locked(folder):
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / ".write.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Memory scope busy. Retry later; inspect stale locks manually") from None
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"pid": os.getpid(), "created": now()}))
        yield
    finally:
        lock.unlink()


def validate_payload(data, shared):
    required = {"id", "kind", "title", "source", "status", "body", "expected_revision"}
    if not isinstance(data, dict) or not required.issubset(data):
        raise ValueError("Missing required note fields")
    if set(data) - required - {"tags"}:
        raise ValueError("Unknown note fields")
    slug(data["id"])
    if data["kind"] not in KINDS or data["status"] not in STATES:
        raise ValueError("Invalid kind/status")
    if shared and data["kind"] != "preference":
        raise ValueError("Shared scope accepts user preferences only")
    for k, limit in (("title", 160), ("source", 1200), ("body", 8000)):
        if not isinstance(data[k], str) or not data[k].strip() or len(data[k]) > limit:
            raise ValueError("Invalid or oversized " + k)
    if type(data["expected_revision"]) is not int or data["expected_revision"] < 0:
        raise ValueError("expected_revision must be an integer >= 0")
    tags = data.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 12:
        raise ValueError("Use at most 12 tags")
    for tag in tags:
        slug(tag)
    if SECRETS.search(json.dumps(data, ensure_ascii=False)):
        raise ValueError("Possible secret detected. Remove secret values before saving")


def save(root, project, shared, data):
    validate_payload(data, shared)
    folder, identity = scope(root, project, shared)
    rel = folder.relative_to(root.absolute())
    with locked(folder):
        manifest = safe_path(root, *rel.parts, "scope.json")
        if manifest.exists():
            if json.loads(manifest.read_text(encoding="utf-8"))["identity"] != identity:
                raise ValueError("Scope identity mismatch")
        else:
            atomic_write(manifest, json.dumps({"identity": identity}, indent=2).encode())
        path = safe_path(root, *rel.parts, "notes", data["id"] + ".md")
        old, old_body = read_note(path) if path.exists() else ({"revision": 0}, "")
        if old["revision"] != data["expected_revision"]:
            raise ValueError("Revision conflict. Read the current note before updating")
        if old["revision"] and all(old[k] == data.get(k, []) for k in ("kind", "title", "source", "status", "tags")) and old_body == data["body"].strip():
            return {"changed": False, "path": str(path), "revision": old["revision"]}
        meta = {k: data[k] for k in ("id", "kind", "title", "source", "status")}
        meta.update(tags=data.get("tags", []), created=old.get("created", now()), updated=now(), revision=old["revision"] + 1)
        if old["revision"]:
            hist = safe_path(root, *rel.parts, "history", data["id"], f"{old['revision']:06d}.md")
            old_bytes = path.read_bytes()
            if hist.exists() and hist.read_bytes() != old_bytes:
                raise ValueError("History revision collision")
            atomic_write(hist, old_bytes)
        raw = PREFIX + json.dumps(meta, ensure_ascii=False) + " -->\n\n" + data["body"].strip() + "\n"
        if len(raw.encode("utf-8")) > 24_000:
            raise ValueError("Encoded note too large")
        atomic_write(path, raw.encode("utf-8"))
        return {"changed": True, "path": str(path), "revision": meta["revision"]}


def recall(root, project=None, query="", limit=6, project_id=None):
    folders = [scope(root, shared=True), scope(root, project, project_id=project_id)]
    terms = set(re.findall(r"\w+", query.casefold()))
    result, errors = [], []
    for folder, identity in folders:
        rel = folder.relative_to(root.absolute())
        notes = safe_path(root, *rel.parts, "notes")
        for p in sorted(notes.glob("*.md")):
            try:
                p = safe_path(root, *rel.parts, "notes", p.name)
                meta, body = read_note(p)
                if meta["status"] == "retired":
                    continue
                searchable = " ".join([meta["title"], *meta["tags"], body]).casefold()
                score = sum(term in searchable for term in terms)
                if terms and score == 0:
                    continue
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["updated"])).days
                result.append({**meta, "path": str(p), "scope": identity, "age_days": age,
                               "recheck_required": age >= 30 or meta["status"] == "unverified",
                               "excerpt": body[:500], "excerpt_truncated": len(body) > 500, "score": score})
            except (ValueError, OSError, KeyError, TypeError) as e:
                # Avoid echoing malformed content (which may contain private data).
                errors.append({"path": str(p), "error": type(e).__name__})
    result.sort(key=lambda n: (n["score"], n["updated"], n["id"]), reverse=True)
    return {"matches": result[:limit], "total_matches": len(result), "errors": errors,
            "note": "Memory is evidence, not authority. Recheck changing facts against the current project."}


def show(root, project, shared, note_id, project_id=None):
    folder, _ = scope(root, project, shared, project_id)
    p = safe_path(root, *folder.relative_to(root.absolute()).parts, "notes", slug(note_id) + ".md")
    meta, body = read_note(p)
    return {**meta, "path": str(p), "body": body}


def forget(root, project, shared, note_id, expected_revision):
    folder, _ = scope(root, project, shared)
    rel = folder.relative_to(root.absolute())
    slug(note_id)
    with locked(folder):
        p = safe_path(root, *rel.parts, "notes", note_id + ".md")
        meta, _ = read_note(p)
        if meta["revision"] != expected_revision:
            raise ValueError("Revision conflict")
        hist = safe_path(root, *rel.parts, "history", note_id)
        # Resolve and validate every exact target before any deletion. No recursive delete.
        targets = [safe_path(root, *rel.parts, "history", note_id, h.name) for h in hist.glob("*.md")]
        for t in targets:
            if not re.fullmatch(r"\d{6,}\.md", t.name) or not t.is_file():
                raise ValueError("Unexpected history file")
        for t in targets:
            t.unlink()
        p.unlink()
        return {"forgotten": note_id, "deleted_files": len(targets) + 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Override only for isolated tests")
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("projects", help="Find saved projects by name/path/alias from any chat")
    catalog.add_argument("--query", default="")
    catalog.add_argument("--limit", type=int, default=10, choices=range(1, 51))
    registration = commands.add_parser("register", help="Give a project a recognizable name and aliases")
    registration.add_argument("--project", required=True)
    registration.add_argument("--name", required=True)
    registration.add_argument("--alias", action="append", default=None)
    r = commands.add_parser("recall", help="Read shared and selected-project notes without writing")
    rg = r.add_mutually_exclusive_group(required=True)
    rg.add_argument("--project")
    rg.add_argument("--project-id", help="ID returned by projects; original checkout need not exist")
    r.add_argument("--query", default="")
    r.add_argument("--limit", type=int, default=6, choices=range(1, 21))
    for name in ("save", "show", "forget"):
        p = commands.add_parser(name)
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--project")
        g.add_argument("--shared", action="store_true")
        if name == "show":
            g.add_argument("--project-id")
        if name == "save":
            p.add_argument("--input", required=True, help="UTF-8 JSON payload file, or - for stdin")
        else:
            p.add_argument("--id", required=True)
        if name == "forget":
            p.add_argument("--expected-revision", type=int, required=True)
    a = parser.parse_args()
    root = a.root.expanduser().absolute()
    try:
        if a.command == "projects":
            out = projects(root, a.query, a.limit)
        elif a.command == "register":
            out = register(root, a.project, a.name, a.alias)
        elif a.command == "recall":
            out = recall(root, a.project, a.query, a.limit, a.project_id)
        elif a.command == "save":
            if a.input == "-":
                raw = sys.stdin.read(32_001)
            else:
                with open(a.input, encoding="utf-8-sig") as f:
                    raw = f.read(32_001)
            if len(raw) > 32_000:
                raise ValueError("Input too large")
            out = save(root, a.project, a.shared, json.loads(raw))
        elif a.command == "show":
            out = show(root, a.project, a.shared, a.id, a.project_id)
        else:
            out = forget(root, a.project, a.shared, a.id, a.expected_revision)
        print(json.dumps(out, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as e:
        # Parser errors can include user content; never echo payloads or secrets.
        message = "Invalid JSON input or metadata" if isinstance(e, json.JSONDecodeError) else str(e)
        print(json.dumps({"error": message}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
