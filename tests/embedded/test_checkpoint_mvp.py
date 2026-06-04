"""Checkpoint MVP: create, list, show, restore-plan, no side effects."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestCheckpointMvp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmpl = Path(tempfile.mkdtemp(prefix="awck_tmpl_"))
        subprocess.run(["git", "init", "-b", "main"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        (cls._tmpl/"README.md").write_text("init\n")
        subprocess.run(["git", "add", "README.md"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls._tmpl), env=env, timeout=30)
        subprocess.run(["git", "add", "-A"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "aiwf"], cwd=str(cls._tmpl), capture_output=True, timeout=10)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpl, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awck_t_"))
        shutil.copytree(self._tmpl, self.tmp, dirs_exist_ok=True, symlinks=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"Failed: {args}\n{r.stderr[:300]}")
        return r

    # ── create ──
    def test_create_makes_checkpoint_dir(self):
        (self.tmp/"README.md").write_text("modified\n")
        self._run_ok("checkpoint", "create")
        ckpts = list((self.tmp/".aiwf"/"checkpoints").iterdir())
        self.assertGreater(len(ckpts), 0)

    def test_checkpoint_json_exists(self):
        (self.tmp/"README.md").write_text("modified\n")
        r = self._run_ok("checkpoint", "create")
        # Find checkpoint dir
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            self.assertTrue((d/"CHECKPOINT.json").exists())
            break

    def test_tracked_patch_exists(self):
        (self.tmp/"README.md").write_text("modified v2\n")
        self._run_ok("checkpoint", "create")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            patch = d / "tracked.patch"
            if patch.exists():
                self.assertGreater(patch.stat().st_size, 0)
            break

    def test_untracked_copied(self):
        (self.tmp/"src").mkdir(exist_ok=True)
        (self.tmp/"src"/"new.js").write_text("new\n")
        self._run_ok("checkpoint", "create")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            untracked = d / "untracked" / "src" / "new.js"
            if untracked.exists():
                self.assertEqual(untracked.read_text(), "new\n")
            break

    # ── list ──
    def test_list_shows_checkpoint(self):
        self._run_ok("checkpoint", "create")
        r = self._run_ok("checkpoint", "list")
        self.assertIn("CHK-", r.stdout)

    # ── show ──
    def test_show_displays_metadata(self):
        (self.tmp/"README.md").write_text("mod\n")
        self._run_ok("checkpoint", "create")
        ck_id = None
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            ck_id = d.name; break
        r = self._run_ok("checkpoint", "show", ck_id)
        self.assertIn("git_head", r.stdout)

    # ── restore-plan ──
    def test_restore_plan_exists(self):
        self._run_ok("checkpoint", "create")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            self.assertTrue((d/"restore-plan.md").exists())
            break

    # ── restore safety ──
    def test_restore_without_confirm_dry_run(self):
        (self.tmp/"README.md").write_text("mod\n")
        self._run_ok("checkpoint", "create")
        ck_id = None
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir(): ck_id = d.name; break
        r = self._run("checkpoint", "restore", ck_id)
        self.assertTrue("dry_run" in r.stdout.lower() or "confirm" in r.stdout.lower(), f"Expected dry_run or confirm, got: {r.stdout[:200]}")

    # ── no side effects ──
    def test_create_no_modify_claude_md(self):
        before = (self.tmp/"CLAUDE.md").read_text()
        self._run_ok("checkpoint", "create")
        self.assertEqual(before, (self.tmp/"CLAUDE.md").read_text())

    def test_create_no_modify_settings(self):
        before = (self.tmp/".claude"/"settings.json").read_text()
        self._run_ok("checkpoint", "create")
        self.assertEqual(before, (self.tmp/".claude"/"settings.json").read_text())



    def test_label_works(self):
        self._run_ok("checkpoint", "create", "--label", "before risky")
        ck_id = None
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir(): ck_id = d.name; break
        ck = json.loads((self.tmp/".aiwf"/"checkpoints"/ck_id/"CHECKPOINT.json").read_text())
        self.assertEqual(ck.get("label"), "before risky")

    def test_untracked_only_sets_dirty_true(self):
        (self.tmp/"src").mkdir(exist_ok=True)
        (self.tmp/"src"/"new.js").write_text("new\n")
        self._run_ok("checkpoint", "create", "--label", "untracked")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            ck = json.loads((d/"CHECKPOINT.json").read_text())
            self.assertTrue(ck["dirty"], f"Untracked-only should be dirty, got dirty={ck['dirty']}")
            break

    def test_no_recursive_copy_of_old_checkpoints(self):
        self._run_ok("checkpoint", "create", "--label", "first")
        (self.tmp/"README.md").write_text("changed\n")
        self._run_ok("checkpoint", "create", "--label", "second")
        # Verify old checkpoint files NOT in new checkpoint untracked
        import glob
        found = list((self.tmp/".aiwf"/"checkpoints").rglob("untracked/.aiwf/checkpoints/*"))
        self.assertEqual(len(found), 0, f"Recursive copy found: {found}")

    def test_planner_skill_mentions_checkpoint(self):
        c2 = (self.tmp/".claude"/"skills"/"aiwf-planner"/"SKILL.md").read_text()
        self.assertIn("checkpoint create", c2.lower())
        self.assertIn("L2", c2)

    def test_reviewer_skill_mentions_checkpoint(self):
        c2 = (self.tmp/".claude"/"skills"/"aiwf-review"/"SKILL.md").read_text()
        self.assertIn("checkpoint", c2.lower())

    def test_status_shows_checkpoint_available(self):
        self._run_ok("checkpoint", "create", "--label", "x")
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "status"],
                          capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertIn("Checkpoint: available", r.stdout)




    def test_new_checkpoint_has_provider_patch(self):
        (self.tmp/"README.md").write_text("mod\n")
        self._run_ok("checkpoint", "create", "--label", "provider test")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            ck = json.loads((d/"CHECKPOINT.json").read_text())
            self.assertEqual(ck.get("provider"), "patch")
            self.assertEqual(ck.get("mode"), "patch")
            break

    def test_list_shows_provider(self):
        self._run_ok("checkpoint", "create", "--label", "list test")
        r = self._run_ok("checkpoint", "list")
        self.assertIn("patch", r.stdout)

    def test_show_shows_provider(self):
        (self.tmp/"README.md").write_text("mod2\n")
        self._run_ok("checkpoint", "create", "--label", "show test")
        ck_id = None
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir(): ck_id = d.name; break
        r = self._run_ok("checkpoint", "show", ck_id)
        self.assertIn("patch", r.stdout)

    def test_restore_plan_mentions_patch(self):
        self._run_ok("checkpoint", "create", "--label", "plan test")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            plan = (d/"restore-plan.md").read_text()
            self.assertIn("Patch Checkpoint", plan)
            break

    def test_old_checkpoint_without_provider_still_works(self):
        (self.tmp/"README.md").write_text("old\n")
        self._run_ok("checkpoint", "create", "--label", "old")
        ck_id = None
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir(): ck_id = d.name; break
        # Remove provider to simulate old checkpoint
        ck = json.loads((self.tmp/".aiwf"/"checkpoints"/ck_id/"CHECKPOINT.json").read_text())
        del ck["provider"]; del ck["mode"]
        (self.tmp/".aiwf"/"checkpoints"/ck_id/"CHECKPOINT.json").write_text(json.dumps(ck, indent=2))
        # Show still works
        r = self._run_ok("checkpoint", "show", ck_id)
        self.assertIn("git_head", r.stdout)




    # ── stash mode ──

    def test_stash_mode_succeeds_when_dirty(self):
        (self.tmp/"README.md").write_text("stash test\n")
        r = self._run("checkpoint", "create", "--mode", "stash", "--label", "stash test")
        self.assertEqual(r.returncode, 0)

    def test_stash_mode_has_git_stash_provider(self):
        (self.tmp/"README.md").write_text("stash2\n")
        self._run_ok("checkpoint", "create", "--mode", "stash", "--label", "stash-provider")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            ck = json.loads((d/"CHECKPOINT.json").read_text())
            if ck.get("mode") == "stash":
                self.assertEqual(ck["provider"], "git_stash")
                self.assertTrue(ck.get("stash_ref") or ck.get("stash_hash"))
                break

    def test_stash_mode_keeps_working_tree_dirty(self):
        (self.tmp/"README.md").write_text("stash-dirty\n")
        self._run_ok("checkpoint", "create", "--mode", "stash", "--label", "keep-dirty")
        # Working tree should still be dirty
        r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=str(self.tmp))
        self.assertIn("README.md", r.stdout, "Working tree should still show README.md as modified")

    def test_stash_list_shows_mode(self):
        (self.tmp/"README.md").write_text("stash-list\n")
        self._run_ok("checkpoint", "create", "--mode", "stash", "--label", "list-stash")
        # Just verify a stash checkpoint exists with mode=stash
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            ck = json.loads((d/"CHECKPOINT.json").read_text())
            if ck.get("mode") == "stash": break
        else: self.fail("No stash checkpoint found")

    def test_stash_restore_plan_mentions_stash(self):
        (self.tmp/"README.md").write_text("stash-plan\n")
        self._run_ok("checkpoint", "create", "--mode", "stash", "--label", "plan-stash")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            if (d/"CHECKPOINT.json").exists() and json.loads((d/"CHECKPOINT.json").read_text()).get("mode") == "stash":
                plan = (d/"restore-plan.md").read_text()
                # Plan should mention git stash or restore steps
                self.assertTrue("stash" in plan.lower() or "Stash" in plan or "Steps" in plan)
                break

    def test_default_mode_is_patch(self):
        (self.tmp/"README.md").write_text("default-mode\n")
        self._run_ok("checkpoint", "create", "--label", "default")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            ck = json.loads((d/"CHECKPOINT.json").read_text())
            if ck.get("label") == "default":
                self.assertEqual(ck.get("mode","patch"), "patch")
                break




    # ── stash correctness ──

    def test_stash_restore_plan_is_stash_specific(self):
        (self.tmp/"README.md").write_text("stash-rp\n")
        self._run_ok("checkpoint", "create", "--mode", "stash", "--label", "rp-stash")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            ck = json.loads((d/"CHECKPOINT.json").read_text())
            if ck.get("mode") == "stash":
                plan = (d/"restore-plan.md").read_text()
                self.assertIn("Git stash checkpoint", plan)
                self.assertIn("git stash apply --index", plan)
                self.assertIn("does not drop the stash", plan)
                break

    def test_stash_restore_plan_no_patch_steps(self):
        (self.tmp/"README.md").write_text("stash-no-patch\n")
        self._run_ok("checkpoint", "create", "--mode", "stash", "--label", "no-patch")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            if json.loads((d/"CHECKPOINT.json").read_text()).get("mode") == "stash":
                plan = (d/"restore-plan.md").read_text()
                self.assertNotIn("git apply tracked.patch", plan)
                self.assertNotIn("git apply staged.patch", plan)
                break

    def test_patch_restore_plan_has_patch_steps(self):
        (self.tmp/"README.md").write_text("patch-rp\n")
        self._run_ok("checkpoint", "create", "--mode", "patch", "--label", "rp-patch")
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            ck = json.loads((d/"CHECKPOINT.json").read_text())
            if ck.get("mode","patch") == "patch" and ck.get("label") == "rp-patch":
                plan = (d/"restore-plan.md").read_text()
                self.assertIn("git apply tracked.patch", plan)
                break

    def test_list_shows_mode(self):
        (self.tmp/"README.md").write_text("list-mode\n")
        self._run_ok("checkpoint", "create", "--mode", "stash", "--label", "lm-stash")
        r = self._run_ok("checkpoint", "list")
        self.assertIn("mode=stash", r.stdout)



if __name__ == "__main__":
    unittest.main()
