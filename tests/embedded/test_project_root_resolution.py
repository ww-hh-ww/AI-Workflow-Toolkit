"""AIWF commands and hooks stay anchored to the installed project root."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 20


class TestProjectRootResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_root_resolution_"))
        self.child = self.tmp / "app" / "Sources"
        self.child.mkdir(parents=True)
        result = self._run(self.tmp, "install", "claude", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, cwd, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

    def test_nested_cli_command_uses_installed_ancestor(self):
        result = self._run(self.child, "plan", "create", "PLAN-NESTED")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.tmp / ".aiwf" / "artifacts" / "plans" / "PLAN-NESTED.md").exists()
        )
        self.assertFalse((self.tmp / "app" / ".aiwf").exists())
        self.assertFalse((self.child / ".aiwf").exists())

    def test_partial_nested_aiwf_does_not_shadow_installed_ancestor(self):
        partial = self.tmp / "app" / ".aiwf" / "state"
        partial.mkdir(parents=True)
        (partial / "state.json").write_text(
            json.dumps({"scope_violation": True}) + "\n", encoding="utf-8"
        )

        result = self._run(self.child, "plan", "create", "PLAN-RECOVERED")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.tmp / ".aiwf" / "artifacts" / "plans" / "PLAN-RECOVERED.md").exists()
        )
        self.assertFalse(
            (self.tmp / "app" / ".aiwf" / "artifacts" / "plans" / "PLAN-RECOVERED.md").exists()
        )

    def test_event_normalizer_uses_installed_ancestor(self):
        from aiwf_core.adapters.claude.normalize_event import normalize

        event = normalize({
            "hook_event_name": "PreToolUse",
            "cwd": str(self.child),
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.tmp / "app" / "Sources" / "File.swift")},
        })

        self.assertEqual(Path(event.cwd), self.tmp.resolve())

    def test_explicit_nested_install_creates_independent_root(self):
        nested_root = self.tmp / "independent"
        nested_root.mkdir()

        result = self._run(nested_root, "install", "claude", "--force")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((nested_root / ".aiwf" / "state" / "state.json").exists())
        self.assertTrue((nested_root / ".claude" / "settings.json").exists())


if __name__ == "__main__":
    unittest.main()
