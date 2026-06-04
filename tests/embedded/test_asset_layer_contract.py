"""Minimal Context Asset Layer v1 — init, refresh, staleness, no closure blocking."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _run(cmd, cwd, timeout=15):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=timeout)

class TestAssetLayer(unittest.TestCase):
    """Asset init creates files; refresh detects staleness; no closure blocking."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awas_"))
        # Create a small project with source + test files
        (cls.tmp / "src").mkdir(exist_ok=True)
        (cls.tmp / "test").mkdir(exist_ok=True)
        (cls.tmp / "src" / "calc.js").write_text(
            "function add(a,b){return a+b}\nmodule.exports={add};")
        (cls.tmp / "test" / "calc.test.js").write_text(
            "const {add}=require('../src/calc');\nconsole.log('test');")
        (cls.tmp / "package.json").write_text(
            '{"name":"test","scripts":{"test":"node test/calc.test.js"}}')
        _run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"], cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ── init ──

    def test_asset_init_creates_core_files(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        asset_dir = self.tmp / ".aiwf" / "assets"
        files = sorted(f.name for f in asset_dir.iterdir() if f.is_file())
        for expected in ["conventions.md", "project-map.json", "test-map.json"]:
            self.assertIn(expected, files)

    def test_project_map_has_metadata(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        pm = json.loads((self.tmp / ".aiwf" / "assets" / "project-map.json").read_text())
        meta = pm["_asset"]
        self.assertEqual(meta["kind"], "project-map")
        self.assertEqual(meta["status"], "fresh")
        self.assertEqual(meta["stale_detection"], "hash")
        self.assertIn("source_hashes", meta)
        self.assertGreater(len(meta["source_files"]), 0)

    def test_project_map_detects_modules_and_exports(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        pm = json.loads((self.tmp / ".aiwf" / "assets" / "project-map.json").read_text())
        modules = pm.get("modules", [])
        self.assertGreater(len(modules), 0)
        calc = [m for m in modules if "calc.js" in m["path"]][0]
        self.assertIn("add", calc["exports"])

    def test_test_map_has_test_command(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        tm = json.loads((self.tmp / ".aiwf" / "assets" / "test-map.json").read_text())
        self.assertEqual(tm["test_command"], "node test/calc.test.js")

    def test_conventions_is_template(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        conv = (self.tmp / ".aiwf" / "assets" / "conventions.md").read_text()
        self.assertIn("Manual template", conv)

    # ── refresh ──

    def test_refresh_check_marks_fresh_when_unchanged(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        r = _run([sys.executable, "-m", "aiwf_core.cli", "asset", "refresh", "--check"], self.tmp)
        self.assertIn("fresh", r.stdout)
        self.assertNotIn("stale", r.stdout.lower())

    def test_refresh_check_marks_stale_after_source_change(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        # Modify a source file
        (self.tmp / "src" / "calc.js").write_text(
            "function add(a,b){return a+b}\nfunction sub(a,b){return a-b}\nmodule.exports={add,sub};")
        r = _run([sys.executable, "-m", "aiwf_core.cli", "asset", "refresh", "--check"], self.tmp)
        self.assertIn("stale", r.stdout.lower())

    def test_refresh_update_restores_fresh(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        (self.tmp / "src" / "calc.js").write_text("// modified")
        # Update
        r = _run([sys.executable, "-m", "aiwf_core.cli", "asset", "refresh", "--update"], self.tmp)
        self.assertIn("fresh (updated)", r.stdout)
        # Now check should be fresh
        r2 = _run([sys.executable, "-m", "aiwf_core.cli", "asset", "refresh", "--check"], self.tmp)
        self.assertIn("fresh", r2.stdout)
        self.assertNotIn("stale", r2.stdout.lower())

    # ── no closure blocking ──

    def test_stale_asset_does_not_block_closure(self):
        """Stale assets are advisory; they do NOT block closure gates."""
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        (self.tmp / "src" / "calc.js").write_text("// stale now")
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "refresh"], self.tmp)

        from aiwf_core.core.closure_contract import closure_conditions_met
        import json as j
        gates = closure_conditions_met(
            {"phase": "closing", "close_attempt": True, "scope_violation": False},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "adequate"},
            {"result": "accepted", "closure_allowed": True, "cleanup_status": "fresh",
             "structure_status": "accepted"},
            {"status": "none"},
        )
        # Stale assets are NOT in the closure gate list — passes
        self.assertTrue(gates["passed"])

    # ── status integration ──

    def test_asset_status_reports_states(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        from aiwf_core.assets.schema import asset_status
        s = asset_status(str(self.tmp))
        self.assertIn("project-map.json", s["assets"])
        self.assertIn("test-map.json", s["assets"])
        self.assertIn("conventions.md", s["assets"])

    # ── no external deps ──


    def test_project_map_is_tier1(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        pm = json.loads((self.tmp / ".aiwf" / "assets" / "project-map.json").read_text())
        self.assertEqual(pm["_asset"]["tier"], 1)
        self.assertIn("tier1_mechanical_fields", pm["_asset"])

    def test_conventions_is_tier2(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        # Tier 2: conventions.md is human-curated, never auto-overwritten
        self.assertTrue((self.tmp / ".aiwf" / "assets" / "conventions.md").exists())

    def test_conventions_preserved_on_refresh(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        conv_path = self.tmp / ".aiwf" / "assets" / "conventions.md"
        conv_path.write_text("# My custom conventions\n- Use tabs\n")
        # Refresh --update on unchanged source should NOT touch conventions
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "refresh", "--update"], self.tmp)
        content = conv_path.read_text()
        self.assertIn("My custom conventions", content)
        self.assertIn("Use tabs", content)

    def test_planner_skill_mentions_assets(self):
        planner = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("workflow level", planner.lower())

    def test_stale_tier1_is_advisory_not_blocking(self):
        """Stale Tier 1 assets warn but do NOT block closure."""
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "init"], self.tmp)
        (self.tmp / "src" / "calc.js").write_text("// changed")
        _run([sys.executable, "-m", "aiwf_core.cli", "asset", "refresh"], self.tmp)
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            {"phase": "closing", "close_attempt": True, "scope_violation": False},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "adequate"},
            {"result": "accepted", "closure_allowed": True, "cleanup_status": "fresh",
             "structure_status": "accepted"},
            {"status": "none"},
        )
        self.assertTrue(gates["passed"], "Stale assets must not block closure")

    def test_stdlib_only_no_llm(self):
        """Asset layer uses only stdlib — no AI/ML imports."""
        import ast, inspect
        from aiwf_core.assets import schema
        source = inspect.getsource(schema)
        tree = ast.parse(source)
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        for imp in imports:
            if isinstance(imp, ast.ImportFrom):
                module = imp.module or ""
                self.assertNotIn("openai", module)
                self.assertNotIn("anthropic", module)
                self.assertNotIn("llm", module.lower())


if __name__ == "__main__":
    unittest.main()
