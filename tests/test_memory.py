import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(os.environ.get("MEMORY_SCRIPT", Path(__file__).resolve().parents[1] / "skills/persistent-memory/scripts/memory.py"))
spec = importlib.util.spec_from_file_location("memory", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "store"
        self.a, self.b = base / "project-a", base / "project-b"
        self.a.mkdir()
        self.b.mkdir()

    def payload(self, **changes):
        p = dict(id="build-command", kind="fact", title="Build command",
                 source="Test fixture, not a real project fact", status="verified",
                 tags=["build"], body="Run fixture-check for this project.", expected_revision=0)
        p.update(changes)
        return p

    def save(self, **changes):
        return m.save(self.root, str(self.a), False, self.payload(**changes))

    def test_recall_does_not_create_any_files(self):
        self.assertEqual(m.recall(self.root, str(self.a))["matches"], [])
        self.assertFalse(self.root.exists())

    def test_create_and_show(self):
        out = self.save()
        self.assertEqual(out["revision"], 1)
        note = m.show(self.root, str(self.a), False, "build-command")
        self.assertIn("fixture-check", note["body"])
        self.assertEqual(note["status"], "verified")

    def test_recall_project_isolation(self):
        self.save()
        self.assertEqual(m.recall(self.root, str(self.b))["matches"], [])

    def test_shared_preferences_visible_to_both_projects(self):
        m.save(self.root, None, True, self.payload(kind="preference", status="user-confirmed"))
        for p in (self.a, self.b):
            self.assertEqual(len(m.recall(self.root, str(p))["matches"]), 1)

    def test_shared_rejects_project_facts(self):
        with self.assertRaises(ValueError):
            m.save(self.root, None, True, self.payload())
        self.assertFalse(self.root.exists())

    def test_history_preserves_exact_previous_bytes(self):
        p = Path(self.save()["path"])
        old = p.read_bytes()
        self.save(body="Changed command", expected_revision=1)
        history = list(self.root.glob("projects/*/history/build-command/*.md"))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].read_bytes(), old)
        self.assertEqual(m.show(self.root, str(self.a), False, "build-command")["revision"], 2)

    def test_duplicate_save_is_noop(self):
        p = Path(self.save()["path"])
        original = p.read_bytes()
        self.assertFalse(self.save(expected_revision=1)["changed"])
        self.assertEqual(original, p.read_bytes())
        self.assertEqual(list(self.root.glob("projects/*/history/**/*.md")), [])

    def test_stale_writer_cannot_overwrite(self):
        p = Path(self.save()["path"])
        before = p.read_bytes()
        with self.assertRaisesRegex(ValueError, "Revision conflict"):
            self.save(body="Wrong overwrite")
        self.assertEqual(before, p.read_bytes())

    def test_lock_blocks_writer(self):
        folder, _ = m.scope(self.root, str(self.a))
        folder.mkdir(parents=True)
        (folder / ".write.lock").write_text("fixture")
        with self.assertRaisesRegex(ValueError, "busy"):
            self.save()
        self.assertEqual((folder / ".write.lock").read_text(), "fixture")

    def test_rejected_write_releases_its_lock(self):
        self.save()
        with self.assertRaises(ValueError):
            self.save()
        self.assertEqual(list(self.root.rglob(".write.lock")), [])

    def test_secret_patterns_rejected_before_disk_write(self):
        for secret in ("password=fixture-secret", "api_key=fixture-secret", "sk-" + "x" * 30,
                       "-----BEGIN PRIVATE KEY-----", "Bearer " + "a" * 30):
            with self.subTest(secret=secret[:10]), self.assertRaisesRegex(ValueError, "secret"):
                self.save(body=secret)
        self.assertFalse(self.root.exists())

    def test_secret_in_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "secret"):
            self.save(source="access_token=fixture-secret")

    def test_id_traversal_rejected(self):
        for value in ("../outside", "a/b", "..", "C:\\escape", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.save(id=value)
        self.assertFalse(self.root.exists())

    def test_oversized_note_rejected(self):
        with self.assertRaises(ValueError):
            self.save(body="x" * 8001)

    def test_missing_source_rejected(self):
        with self.assertRaises(ValueError):
            self.save(source="")

    def test_retired_note_excluded_but_history_available(self):
        self.save()
        self.save(status="retired", expected_revision=1)
        self.assertEqual(m.recall(self.root, str(self.a))["matches"], [])
        self.assertEqual(len(list(self.root.glob("projects/*/history/*/*.md"))), 1)

    def test_unverified_note_flagged(self):
        self.save(status="unverified")
        self.assertTrue(m.recall(self.root, str(self.a))["matches"][0]["recheck_required"])

    def test_old_note_flagged(self):
        p = Path(self.save()["path"])
        meta, body = m.read_note(p)
        meta["updated"] = "2020-01-01T00:00:00+00:00"
        p.write_text(m.PREFIX + json.dumps(meta) + " -->\n\n" + body, encoding="utf-8")
        self.assertTrue(m.recall(self.root, str(self.a))["matches"][0]["recheck_required"])

    def test_keyword_filter_and_result_limit(self):
        for i in range(4):
            self.save(id=f"note-{i}", body="matched keyword" if i < 3 else "different")
        out = m.recall(self.root, str(self.a), "matched", limit=2)
        self.assertEqual(len(out["matches"]), 2)
        self.assertEqual(out["total_matches"], 3)

    def test_unicode_roundtrip(self):
        body = "مرحبا بالعالم 中文 café"
        self.save(body=body)
        self.assertEqual(m.show(self.root, str(self.a), False, "build-command")["body"], body)

    def test_malformed_note_reported_not_silently_ignored(self):
        p = Path(self.save()["path"])
        p.write_text("broken private content", encoding="utf-8")
        out = m.recall(self.root, str(self.a))
        self.assertEqual(len(out["errors"]), 1)
        self.assertNotIn("private content", json.dumps(out))

    def test_forget_removes_current_and_history_only_for_selected_note(self):
        self.save()
        self.save(body="Revision two", expected_revision=1)
        self.save(id="keep-me")
        out = m.forget(self.root, str(self.a), False, "build-command", 2)
        self.assertEqual(out["deleted_files"], 2)
        self.assertFalse(list(self.root.glob("projects/*/history/build-command/*.md")))
        self.assertEqual([n["id"] for n in m.recall(self.root, str(self.a))["matches"]], ["keep-me"])

    def test_forget_stale_revision_preserves_data(self):
        self.save()
        with self.assertRaises(ValueError):
            m.forget(self.root, str(self.a), False, "build-command", 0)
        self.assertEqual(len(m.recall(self.root, str(self.a))["matches"]), 1)

    def test_same_path_spelling_maps_to_same_scope(self):
        self.assertEqual(m.scope(self.root, str(self.a)), m.scope(self.root, str(self.a / ".")))
        if os.name == "nt":
            self.assertEqual(m.scope(self.root, str(self.a)), m.scope(self.root, str(self.a).upper()))

    def test_invalid_project_does_not_create_store(self):
        with self.assertRaises(OSError):
            m.recall(self.root, str(self.a / "missing"))
        self.assertFalse(self.root.exists())

    def test_history_collision_rejected_without_overwrite(self):
        p = Path(self.save()["path"])
        before = p.read_bytes()
        hist = p.parent.parent / "history/build-command/000001.md"
        hist.parent.mkdir(parents=True)
        hist.write_bytes(b"different revision")
        with self.assertRaisesRegex(ValueError, "collision"):
            self.save(body="new", expected_revision=1)
        self.assertEqual(p.read_bytes(), before)

    def test_cli_separate_process_save_and_recall(self):
        cmd = [sys.executable, str(SCRIPT), "--root", str(self.root)]
        proc = subprocess.run(cmd + ["save", "--project", str(self.a), "--input", "-"],
                              input=json.dumps(self.payload()), text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = subprocess.run(cmd + ["recall", "--project", str(self.a), "--query", "fixture-check"],
                              text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["matches"][0]["id"], "build-command")

    def test_cli_error_has_nonzero_status_without_payload(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "save",
                               "--project", str(self.a), "--input", "-"],
                              input='{"private_bad_json":', text=True, capture_output=True)
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn("private_bad_json", proc.stderr)

    def test_project_catalog_is_read_only_and_empty_initially(self):
        self.assertEqual(m.projects(self.root)["projects"], [])
        self.assertFalse(self.root.exists())

    def test_catalog_discovers_existing_notes_without_migration(self):
        self.save()
        catalog = m.projects(self.root, "project-a")
        self.assertEqual(catalog["total_matches"], 1)
        self.assertTrue(catalog["projects"][0]["has_notes"])
        self.assertNotIn("fixture-check", json.dumps(catalog))
        self.assertFalse(catalog["requires_selection"])

    def test_named_projects_and_aliases(self):
        result = m.register(self.root, str(self.a), "Project X", ["旧项目", "Client Portal"])
        for query in ("Project X", "旧项目", "client portal"):
            self.assertEqual(m.projects(self.root, query)["projects"][0]["project_id"], result["project_id"])
        self.save()
        self.assertEqual(m.projects(self.root, "Project X")["projects"][0]["name"], "Project X")

    def test_register_is_noop_and_preserves_aliases_when_omitted(self):
        m.register(self.root, str(self.a), "X", ["alias"])
        self.assertFalse(m.register(self.root, str(self.a), "X")["changed"])
        self.assertEqual(m.projects(self.root, "alias")["total_matches"], 1)

    def test_ambiguous_names_require_selection(self):
        for p in (self.a, self.b):
            m.register(self.root, str(p), "Project X")
        out = m.projects(self.root, "Project X", limit=1)
        self.assertEqual(out["total_matches"], 2)
        self.assertTrue(out["requires_selection"])

    def test_cross_project_recall_is_explicit_and_scoped(self):
        self.save(body="Only Project A has this decision")
        m.save(self.root, str(self.b), False, self.payload(body="Only Project B has this decision"))
        project_id = m.projects(self.root, "project-a")["projects"][0]["project_id"]
        out = m.recall(self.root, project_id=project_id)
        self.assertIn("Project A", out["matches"][0]["excerpt"])
        self.assertNotIn("Project B", json.dumps(out))
        self.assertIn("Project B", m.recall(self.root, str(self.b))["matches"][0]["excerpt"])

    def test_saved_project_read_survives_checkout_removal(self):
        self.save()
        project_id = m.projects(self.root, "project-a")["projects"][0]["project_id"]
        self.a.rmdir()  # Empty test fixture only. Memory lives outside the checkout.
        self.assertEqual(len(m.recall(self.root, project_id=project_id)["matches"]), 1)
        self.assertIn("fixture-check", m.show(self.root, None, False, "build-command", project_id)["body"])

    def test_saved_project_id_rejects_traversal_and_conflicting_scope(self):
        with self.assertRaises(ValueError):
            m.recall(self.root, project_id="../shared")
        with self.assertRaises(ValueError):
            m.recall(self.root, str(self.a), project_id="a" * 24)

    def test_catalog_reports_bad_metadata_without_leaking_content(self):
        self.save()
        folder, _ = m.scope(self.root, str(self.a))
        (folder / "scope.json").write_text('bad-private-content', encoding="utf-8")
        out = m.projects(self.root)
        self.assertEqual(len(out["errors"]), 1)
        self.assertNotIn("bad-private-content", json.dumps(out))

    def test_registry_rejects_mismatched_identity(self):
        self.save()
        folder, _ = m.scope(self.root, str(self.a))
        (folder / "scope.json").write_text(json.dumps({"identity": str(self.b)}), encoding="utf-8")
        with self.assertRaises(ValueError):
            m.recall(self.root, project_id=folder.name)

    def test_new_process_in_different_workspace_finds_project_by_name(self):
        self.save(id="project-overview", body="Project X: used tests first; last step was validating the parser.")
        m.register(self.root, str(self.a), "Project X")
        cmd = [sys.executable, str(SCRIPT.resolve()), "--root", str(self.root)]
        result = subprocess.run(cmd + ["projects", "--query", "Project X"], cwd=self.b,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        project_id = json.loads(result.stdout)["projects"][0]["project_id"]
        result = subprocess.run(cmd + ["show", "--project-id", project_id, "--id", "project-overview"],
                                cwd=self.b, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("used tests first", json.loads(result.stdout)["body"])

    def test_project_labels_reject_obvious_secrets(self):
        with self.assertRaisesRegex(ValueError, "secret"):
            m.register(self.root, str(self.a), "Project X", ["password=fixture-secret"])
        self.assertFalse(self.root.exists())

    def test_symlink_escape_rejected(self):
        folder, _ = m.scope(self.root, str(self.a))
        folder.mkdir(parents=True)
        try:
            (folder / "notes").symlink_to(self.b, target_is_directory=True)
        except OSError as e:
            self.skipTest("Symlink creation unavailable: " + str(e.winerror if hasattr(e, 'winerror') else e.errno))
        with self.assertRaisesRegex(ValueError, "links"):
            self.save()
        self.assertEqual(list(self.b.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_windows_junction_escape_rejected(self):
        folder, _ = m.scope(self.root, str(self.a))
        folder.mkdir(parents=True)
        link = folder / "notes"
        env = {**os.environ, "MEMORY_TEST_LINK": str(link), "MEMORY_TEST_TARGET": str(self.b)}
        proc = subprocess.run(["powershell", "-NoProfile", "-Command",
                               "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:MEMORY_TEST_LINK -Target $env:MEMORY_TEST_TARGET | Out-Null"],
                              env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        try:
            self.assertTrue(link.is_junction())
            with self.assertRaisesRegex(ValueError, "junctions"):
                self.save()
            self.assertEqual(list(self.b.iterdir()), [])
        finally:
            # Remove only the verified fixture junction, never recurse into its target.
            if link.is_junction() and link.parent.resolve() == folder.resolve():
                link.rmdir()


if __name__ == "__main__":
    unittest.main(verbosity=2)
