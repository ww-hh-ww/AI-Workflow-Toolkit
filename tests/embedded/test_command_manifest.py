"""Command Manifest contract tests — prevent command surface rot."""
import os, subprocess, sys, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestCommandManifest(unittest.TestCase):
    """Verify COMMAND_MANIFEST stays consistent with the parser and help output.

    Design: in-process checks for structure; subprocess smoke for primary
    and a sample of deprecated commands only. Full subprocess sweep over
    all 28 commands is too heavy and causes CI noise.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        cls.manifest_path = PROJECT_ROOT / "aiwf_core" / "core" / "command_manifest.py"
        spec = importlib.util.spec_from_file_location("command_manifest", str(cls.manifest_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls.manifest = mod.COMMAND_MANIFEST
        cls.PRIMARY = mod.PRIMARY
        cls.ADVANCED = mod.ADVANCED
        cls.INTERNAL = mod.INTERNAL
        cls.DEPRECATED = mod.DEPRECATED
        cls.QUARANTINE = mod.QUARANTINE

    def _parser_commands(self):
        from aiwf_core.commands.parser import build_parser
        parser = build_parser(None)
        if hasattr(parser, '_subparsers') and parser._subparsers:
            return set(parser._subparsers._group_actions[0].choices.keys())
        return set()

    def _run_help(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args, "--help"],
            capture_output=True, text=True, env=env, timeout=10,
        )

    # ── in-process checks ──

    def test_next_command_in_manifest(self):
        self.assertIn("next", self.manifest,
                      "'next' is a top-level CLI command but missing from COMMAND_MANIFEST")

    def test_parser_top_level_commands_in_manifest(self):
        missing = self._parser_commands() - set(self.manifest.keys())
        self.assertEqual(set(), missing,
                         f"Parser commands missing from COMMAND_MANIFEST: {missing}")

    def test_manifest_commands_in_parser(self):
        """Every manifest command must be reachable via parser (in-process, not subprocess)."""
        parser_cmds = self._parser_commands()
        manifest_cmds = set(self.manifest.keys())
        missing_from_parser = manifest_cmds - parser_cmds
        self.assertEqual(set(), missing_from_parser,
                         f"Manifest commands not in parser: {missing_from_parser}")

    def test_every_manifest_entry_has_required_fields(self):
        required = {"tier", "core", "caller", "trigger", "visible", "tested", "keep"}
        for cmd, entry in self.manifest.items():
            missing = required - set(entry.keys())
            self.assertEqual(set(), missing,
                             f"Command '{cmd}' missing required fields: {missing}")
            self.assertIn(entry["tier"], [self.PRIMARY, self.ADVANCED, self.INTERNAL, self.DEPRECATED, self.QUARANTINE])
            self.assertIn(entry.get("core", "") or "", 
                         ["active_plan", "boundary", "verification", "goal_progress", "recovery", "infra", ""])

    def test_primary_count_not_inflated(self):
        primary_cmds = [k for k, v in self.manifest.items() if v["tier"] == self.PRIMARY]
        self.assertLessEqual(len(primary_cmds), 12,
                             f"Primary commands inflated: {len(primary_cmds)}. Current: {sorted(primary_cmds)}")

    def test_manifest_summary_runs(self):
        from aiwf_core.core.command_manifest import manifest_summary
        summary = manifest_summary()
        self.assertIn("PRIMARY", summary)
        self.assertIn("ADVANCED", summary)
        self.assertIn("DEPRECATED", summary)
        self.assertIn("QUARANTINE", summary)

    # ── subprocess smoke: primary + sample only ──

    def test_primary_commands_smoke(self):
        """Smoke-test: each primary command returns clean --help output."""
        primary_cmds = [k for k, v in self.manifest.items() if v["tier"] == self.PRIMARY]
        failed = []
        for cmd in primary_cmds:
            r = self._run_help(cmd)
            if r.returncode != 0:
                failed.append(f"{cmd} (exit={r.returncode})")
        self.assertEqual([], failed, f"Primary commands failed --help: {failed}")

    def test_default_help_shows_only_primary(self):
        """aiwf --help must only show primary-tier commands."""
        r = self._run_help()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.lower()

        primary_cmds = {k for k, v in self.manifest.items() if v["tier"] == self.PRIMARY}
        advanced_cmds = {k for k, v in self.manifest.items() if v["tier"] == self.ADVANCED}
        internal_cmds = {k for k, v in self.manifest.items() if v["tier"] == self.INTERNAL}
        quarantine_cmds = {k for k, v in self.manifest.items() if v["tier"] == self.QUARANTINE}

        for cmd in advanced_cmds | internal_cmds | quarantine_cmds:
            self.assertNotIn(f" {cmd} ", out,
                             f"Non-primary command '{cmd}' should not appear in default help")
        for cmd in primary_cmds:
            self.assertIn(cmd, out, f"Primary command '{cmd}' must appear in default help")

    def test_all_help_shows_advanced(self):
        """aiwf --help --all must show advanced commands."""
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "--help", "--all"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(PROJECT_ROOT), **os.environ}, timeout=10,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.lower()
        advanced_cmds = {k for k, v in self.manifest.items() if v["tier"] == self.ADVANCED}
        for cmd in advanced_cmds:
            self.assertIn(cmd, out, f"Advanced command '{cmd}' must appear in --help --all")

    def test_deprecated_commands_emit_warning(self):
        """Smoke first 2 deprecated/quarantine commands for warning emission."""
        deprecated_cmds = [k for k, v in self.manifest.items() if v["tier"] in (self.DEPRECATED, self.QUARANTINE)]
        self.assertTrue(len(deprecated_cmds) > 0, "Expected at least one deprecated/quarantine command")

        for cmd in deprecated_cmds[:2]:  # Smoke first 2 only
            r = self._run_help(cmd)
            combined = (r.stdout + r.stderr).lower()
            deprecation_msg = self.manifest[cmd].get("deprecation", "").lower()
            if deprecation_msg:
                key_word = deprecation_msg.split()[0] if deprecation_msg.split() else "deprecated"
                self.assertTrue(
                    "warning" in combined or "deprecat" in combined or key_word in combined,
                    f"Deprecated '{cmd}' must emit warning. stdout={r.stdout[:200]} stderr={r.stderr[:200]}"
                )


if __name__ == "__main__":
    unittest.main()
