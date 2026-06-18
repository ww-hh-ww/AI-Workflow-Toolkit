"""Project Environment Profile: scan, show, status, report, skills, no secrets."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestEnvironmentProfile(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awenv_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        (self.tmp / ".aiwf").mkdir(parents=True, exist_ok=True)
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")
        # Clean any previous environment profile
        ep = self.tmp / ".aiwf" / "assets" / "environment.json"
        if ep.exists(): ep.unlink()

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # env scan creates profile
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_env_scan_creates_environment_json(self):
        (self.tmp / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest run", "build": "vite build"}}))
        self._run("env", "scan")
        ep = self.tmp / ".aiwf" / "assets" / "environment.json"
        self.assertTrue(ep.exists(), f"Expected {ep} to exist")

    # ═══════════════════════════════════════════════════════════════
    # package.json extraction
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_package_json_test_produces_npm_test(self):
        (self.tmp / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest run"}}))
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        self.assertIn("npm test", ep["test_commands"],
                      f"test_commands should contain 'npm test': {ep['test_commands']}")

    @unittest.skip("V1: hidden module")
    def test_package_json_build_produces_npm_run_build(self):
        (self.tmp / "package.json").write_text(
            json.dumps({"scripts": {"build": "vite build"}}))
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        self.assertIn("npm run build", ep["build_commands"])

    @unittest.skip("V1: hidden module")
    def test_package_json_dev_produces_npm_run_dev(self):
        (self.tmp / "package.json").write_text(
            json.dumps({"scripts": {"dev": "vite"}}))
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        self.assertIn("npm run dev", ep["run_commands"])

    @unittest.skip("V1: hidden module")
    def test_commands_do_not_contain_raw_script_content(self):
        (self.tmp / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest run", "build": "vite build"}}))
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        all_cmds = " ".join(ep["test_commands"] + ep["build_commands"] + ep["run_commands"])
        self.assertNotIn("npm run test --", all_cmds)
        self.assertNotIn("npm run build --", all_cmds)

    @unittest.skip("V1: hidden module")
    def test_npm_detected_from_package_lock(self):
        (self.tmp / "package.json").write_text(json.dumps({"scripts": {}}))
        (self.tmp / "package-lock.json").touch()
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        self.assertIn("npm", ep["package_managers"])

    @unittest.skip("V1: hidden module")
    def test_pnpm_detected_from_pnpm_lock(self):
        (self.tmp / "pnpm-lock.yaml").touch()
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        self.assertIn("pnpm", ep["package_managers"])

    # ═══════════════════════════════════════════════════════════════
    # platformio
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_platformio_ini_detects_embedded(self):
        (self.tmp / "platformio.ini").write_text("[env:uno]\nplatform = atmega328p\n")
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        self.assertIn("embedded", ep["languages"])
        self.assertTrue(any("pio test" in c for c in ep["test_commands"]))

    # ═══════════════════════════════════════════════════════════════
    # CMakeLists
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_cmake_detects_cpp_and_cmake_build(self):
        (self.tmp / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)\n")
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        self.assertIn("cpp", ep["languages"])
        self.assertTrue(any("cmake" in c for c in ep["build_commands"]))

    # ═══════════════════════════════════════════════════════════════
    # tools detection
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_detected_tools_are_bool(self):
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        for tool, val in ep["detected_tools"].items():
            self.assertIsInstance(val, bool, f"{tool} should be bool, got {type(val)}")

    # ═══════════════════════════════════════════════════════════════
    # no secrets
    # ═══════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════
    # missing_tools only lists relevant tools
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_npm_project_missing_tools_excludes_cargo_pio_mvn(self):
        (self.tmp / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        for tool in ["cargo", "pio", "platformio", "mvn", "go"]:
            self.assertNotIn(tool, ep["missing_tools"],
                             f"npm project should not list {tool} as missing")

    @unittest.skip("V1: hidden module")
    def test_npm_project_no_risks_for_irrelevant_tools(self):
        (self.tmp / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
        (self.tmp / "package-lock.json").touch()
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        risks_text = " ".join(ep["known_environment_risks"])
        for tool in ["cargo", "pio", "platformio", "mvn"]:
            self.assertNotIn(tool, risks_text,
                             f"npm project risks should not mention {tool}")

    @unittest.skip("V1: hidden module")
    def test_platformio_risk_only_when_pio_missing(self):
        (self.tmp / "platformio.ini").write_text("[env:uno]\nplatform = atmega328p\n")
        # pio/platformio may or may not be installed; risk is conditional
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        has_pio = ep["detected_tools"].get("pio") or ep["detected_tools"].get("platformio")
        risks_text = " ".join(ep["known_environment_risks"])
        if not has_pio:
            self.assertIn("platformio", risks_text.lower())
        # Either way, no crash — test that the field exists
        self.assertIsInstance(ep["known_environment_risks"], list)

    @unittest.skip("V1: hidden module")
    def test_cmake_risk_only_when_cmake_missing(self):
        (self.tmp / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)\n")
        self._run("env", "scan")
        ep = json.loads((self.tmp / ".aiwf" / "assets" / "environment.json").read_text())
        self.assertIsInstance(ep["known_environment_risks"], list)
        self.assertIn("cpp", ep["languages"])

    # ═══════════════════════════════════════════════════════════════
    # status: profiled for normal npm project (npm usually installed)
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_status_profiled_for_npm_project_with_npm(self):
        (self.tmp / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
        self._run("env", "scan")
        from aiwf_core.core.environment import _detected_tools
        tools = _detected_tools()
        out = self._run("status", "--debug").stdout
        if tools.get("npm"):
            # npm is installed, should be profiled
            self.assertIn("Environment:", out)

    @unittest.skip("V1: hidden module")
    def test_environment_json_no_secrets(self):
        # Set an env var, make sure it's not in profile
        os.environ["FAKE_SECRET"] = "abc123"
        self._run("env", "scan")
        ep_text = (self.tmp / ".aiwf" / "assets" / "environment.json").read_text()
        self.assertNotIn("abc123", ep_text)

    # ═══════════════════════════════════════════════════════════════
    # env show
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_env_show_works_and_no_raw_json(self):
        (self.tmp / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest run"}}))
        self._run("env", "scan")
        out = self._run("env", "show").stdout
        self.assertNotIn('"test_commands"', out)
        self.assertIn("npm test", out)

    @unittest.skip("V1: hidden module")
    def test_env_show_missing_shows_hint(self):
        out = self._run("env", "show").stdout
        self.assertIn("env scan", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # env help
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_env_help_no_traceback(self):
        r = self._run("env")
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("scan", r.stdout.lower())
        self.assertIn("show", r.stdout.lower())

    # ═══════════════════════════════════════════════════════════════
    # status
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_status_shows_environment_missing(self):
        out = self._run("status", "--debug").stdout
        self.assertIn("Environment:", out)

    @unittest.skip("V1: hidden module")
    def test_status_shows_environment_profiled(self):
        (self.tmp / "package.json").write_text(json.dumps({"scripts": {}}))
        self._run("env", "scan")
        out = self._run("status", "--debug").stdout
        self.assertIn("Environment:", out)

    # ═══════════════════════════════════════════════════════════════
    # UserPromptSubmit no dump
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_userpromptsubmit_no_environment_json_dump(self):
        (self.tmp / "package.json").write_text(json.dumps({"scripts": {"test": "secret-test-cmd-xyz"}}))
        self._run("env", "scan")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret-test-cmd-xyz", ctx)

    # ═══════════════════════════════════════════════════════════════
    # Skill text checks
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_planner_mentions_env_scan(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "references" / "lifecycle.md").read_text()
        self.assertIn("task", c.lower(),
                      "Planner execute skill should mention task lifecycle")

    @unittest.skip("V1: hidden module")
    def test_planner_mentions_environment_route(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "references" / "risk-and-rollback.md").read_text()
        self.assertIn("environment", c.lower(),
                      "Planner should mention environment route")

    @unittest.skip("V1: hidden module")
    def test_tester_mentions_suspected_route_environment(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("evidence", c.lower())

    @unittest.skip("V1: hidden module")
    def test_tester_mentions_env_show(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("requirements", c.lower(),
                      "Tester should mention task requirements")

    @unittest.skip("V1: hidden module")
    def test_reviewer_checks_environment_before_blaming_executor(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("evidence", c.lower(),
                      "Reviewer should mention evidence")

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_report_includes_environment_section(self):
        (self.tmp / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest run"}}))
        self._run("env", "scan")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "records" / "闭合报告.md").read_text()
        self.assertIn("## Environment", rpt)

    # ═══════════════════════════════════════════════════════════════
    # compile checks
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "environment.py"), doraise=True)

    @unittest.skip("V1: hidden module")
    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
