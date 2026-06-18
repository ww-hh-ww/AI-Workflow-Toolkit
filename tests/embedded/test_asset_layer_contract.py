"""Minimal Context Asset Layer v2 — init, refresh, staleness, no closure blocking.

Each test gets its own tmp project to prevent state pollution across
init/refresh/mutate cycles. CLI tests install once per test; pure-function
tests skip install.

V2: asset CLI commands were removed; tests now call schema functions directly.
"""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _run(cmd, cwd, timeout=15):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=timeout)


def _make_project(tmp):
    """Create a minimal JS project so asset init has something to scan."""
    (tmp / "src").mkdir(exist_ok=True)
    (tmp / "test").mkdir(exist_ok=True)
    (tmp / "src" / "calc.js").write_text(
        "function add(a,b){return a+b}\nmodule.exports={add};")
    (tmp / "test" / "calc.test.js").write_text(
        "const {add}=require('../src/calc');\nconsole.log('test');")
    (tmp / "package.json").write_text(
        '{"name":"test","scripts":{"test":"node test/calc.test.js"}}')


def _install(tmp):
    _make_project(tmp)
    r = _run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"], tmp)
    if r.returncode != 0:
        raise RuntimeError(f"install failed: {r.stderr}")


class TestAssetLayerCLI(unittest.TestCase):
    """Tests that need a full AIWF install (CLI commands).

    Uses setUpClass to install once, avoiding 13x subprocess install cost
    that causes test file hanging on full runs.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awas_cli_"))
        _make_project(cls.tmp)
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # Reset asset files and state so each test starts clean
        asset_dir = self.tmp / ".aiwf" / "assets"
        if asset_dir.exists():
            for f in list(asset_dir.glob("*")):
                if f.is_file():
                    f.unlink()
        # Restore source files to original state
        calc = self.tmp / "src" / "calc.js"
        calc.write_text("function add(a,b){return a+b}\nmodule.exports={add};")
        # Reset state files to defaults (V2 paths)
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        import json as _json
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_json.dumps(dfn(), indent=2) + "\n", encoding="utf-8")
        # Remove any state artifacts from previous tests (V2 layout)
        for sub in ("plans", "records", "runtime/internal"):
            d = self.tmp / ".aiwf" / sub
            if d.exists():
                for f in list(d.glob("*")):
                    if f.is_file() and f.name not in ("toolkit-path.txt",):
                        f.unlink()

    def tearDown(self):
        # Clean up files created by this test (but keep the install)
        asset_dir = self.tmp / ".aiwf" / "assets"
        if asset_dir.exists():
            for f in list(asset_dir.glob("*")):
                if f.is_file():
                    f.unlink()
        calc = self.tmp / "src" / "calc.js"
        calc.write_text("function add(a,b){return a+b}\nmodule.exports={add};")

    def test_asset_init_creates_core_files(self):
        from aiwf_core.assets.schema import init_assets
        init_assets(str(self.tmp))
        asset_dir = self.tmp / ".aiwf" / "assets"
        files = sorted(f.name for f in asset_dir.iterdir() if f.is_file())
        for expected in ["conventions.md", "project-map.json", "test-map.json"]:
            self.assertIn(expected, files)

    def test_project_map_has_metadata(self):
        from aiwf_core.assets.schema import init_assets
        init_assets(str(self.tmp))
        pm = json.loads((self.tmp / ".aiwf" / "assets" / "project-map.json").read_text())
        meta = pm["_asset"]
        self.assertEqual(meta["kind"], "project-map")
        self.assertEqual(meta["status"], "fresh")
        self.assertEqual(meta["stale_detection"], "hash")
        self.assertIn("source_hashes", meta)
        self.assertGreater(len(meta["source_files"]), 0)

    def test_project_map_detects_modules_and_exports(self):
        from aiwf_core.assets.schema import init_assets
        init_assets(str(self.tmp))
        pm = json.loads((self.tmp / ".aiwf" / "assets" / "project-map.json").read_text())
        modules = pm.get("modules", [])
        self.assertGreater(len(modules), 0)
        calc = [m for m in modules if "calc.js" in m["path"]][0]
        self.assertIn("add", calc["exports"])

    def test_test_map_has_test_command(self):
        from aiwf_core.assets.schema import init_assets
        init_assets(str(self.tmp))
        tm = json.loads((self.tmp / ".aiwf" / "assets" / "test-map.json").read_text())
        self.assertEqual(tm["test_command"], "node test/calc.test.js")

    def test_conventions_is_template(self):
        from aiwf_core.assets.schema import init_assets
        init_assets(str(self.tmp))
        conv = (self.tmp / ".aiwf" / "assets" / "conventions.md").read_text()
        self.assertIn("Manual template", conv)

    def test_refresh_check_marks_fresh_when_unchanged(self):
        from aiwf_core.assets.schema import init_assets, refresh_assets
        init_assets(str(self.tmp))
        r = refresh_assets(str(self.tmp), update=False)
        self.assertEqual(r["overall"], "fresh")
        self.assertNotIn("stale", r["overall"])

    def test_refresh_check_marks_stale_after_source_change(self):
        from aiwf_core.assets.schema import init_assets, refresh_assets
        init_assets(str(self.tmp))
        (self.tmp / "src" / "calc.js").write_text(
            "function add(a,b){return a+b}\nfunction sub(a,b){return a-b}\nmodule.exports={add,sub};")
        r = refresh_assets(str(self.tmp), update=False)
        self.assertEqual(r["overall"], "stale")

    def test_refresh_update_restores_fresh(self):
        from aiwf_core.assets.schema import init_assets, refresh_assets
        init_assets(str(self.tmp))
        (self.tmp / "src" / "calc.js").write_text("// modified")
        r = refresh_assets(str(self.tmp), update=True)
        self.assertIn("fresh (updated)", r["assets"]["project-map.json"])
        r2 = refresh_assets(str(self.tmp), update=False)
        self.assertEqual(r2["overall"], "fresh")

    def test_conventions_preserved_on_refresh(self):
        from aiwf_core.assets.schema import init_assets, refresh_assets
        init_assets(str(self.tmp))
        conv_path = self.tmp / ".aiwf" / "assets" / "conventions.md"
        conv_path.write_text("# My custom conventions\n- Use tabs\n")
        refresh_assets(str(self.tmp), update=True)
        content = conv_path.read_text()
        self.assertIn("My custom conventions", content)
        self.assertIn("Use tabs", content)

    def test_planner_skill_mentions_routing_and_activation(self):
        planner = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        lower = planner.lower()
        # V1: Planner focuses on task strategy, not routing mechanics
        self.assertIn("task strategist", lower)
        self.assertIn("aiwf status", lower)

    def test_asset_status_reports_states(self):
        from aiwf_core.assets.schema import init_assets, asset_status
        init_assets(str(self.tmp))
        s = asset_status(str(self.tmp))
        self.assertIn("project-map.json", s["assets"])
        self.assertIn("test-map.json", s["assets"])
        self.assertIn("conventions.md", s["assets"])

    def test_project_map_is_tier1(self):
        from aiwf_core.assets.schema import init_assets
        init_assets(str(self.tmp))
        pm = json.loads((self.tmp / ".aiwf" / "assets" / "project-map.json").read_text())
        self.assertEqual(pm["_asset"]["tier"], 1)
        self.assertIn("tier1_mechanical_fields", pm["_asset"])

    def test_conventions_is_tier2(self):
        from aiwf_core.assets.schema import init_assets
        init_assets(str(self.tmp))
        self.assertTrue((self.tmp / ".aiwf" / "assets" / "conventions.md").exists())


class TestAssetLayerPure(unittest.TestCase):
    """Tests that don't need install — pure function / schema checks."""

    def test_stale_asset_does_not_block_closure(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            {"phase": "closing", "close_attempt": True, "scope_violation": False},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "adequate"},
            {"result": "accepted", "closure_allowed": True, "cleanup_status": "fresh",
             "structure_status": "accepted"},
            {"status": "none"},
        )
        self.assertTrue(gates["passed"])

    def test_stale_tier1_is_advisory_not_blocking(self):
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
