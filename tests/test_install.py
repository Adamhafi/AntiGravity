import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "Home With Spaces"

    def test_dry_run_creates_nothing(self):
        result = installer.install(self.home, dry_run=True)
        self.assertEqual(len(result["files"]), 3)
        self.assertFalse(self.home.exists())

    def test_installs_rendered_paths_without_memories(self):
        result = installer.install(self.home)
        self.assertEqual(len(result["created"]), 3)
        for path in result["files"]:
            content = Path(path).read_text(encoding="utf-8")
            self.assertNotIn("{{SKILL_DIR}}", content)
            self.assertNotIn("{{MEMORY_DIR}}", content)
        skill = self.home / ".gemini/config/skills/persistent-memory/SKILL.md"
        self.assertIn(self.home.as_posix(), skill.read_text(encoding="utf-8"))
        self.assertFalse((self.home / ".gemini/antigravity-ide/user-memory").exists())

    def test_repeat_install_is_noop(self):
        installer.install(self.home)
        self.assertEqual(installer.install(self.home)["created"], [])

    def test_conflict_preserves_existing_file_and_writes_nothing_else(self):
        p = self.home / ".gemini/config/rules/persistent-memory.md"
        p.parent.mkdir(parents=True)
        p.write_text("customized by user", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs"):
            installer.install(self.home)
        self.assertEqual(p.read_text(encoding="utf-8"), "customized by user")
        self.assertFalse((self.home / ".gemini/config/skills").exists())

    def test_existing_persona_and_settings_unchanged(self):
        for rel in (".gemini/GEMINI.md", ".gemini/config/config.json"):
            p = self.home / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"existing user configuration")
        installer.install(self.home)
        for rel in (".gemini/GEMINI.md", ".gemini/config/config.json"):
            self.assertEqual((self.home / rel).read_bytes(), b"existing user configuration")


if __name__ == "__main__":
    unittest.main(verbosity=2)
