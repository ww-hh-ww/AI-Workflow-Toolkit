import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.embedded import test_experimenter_contract as fixtures
from aiwf_core.core.experiment_assets import experiment_assets, experiment_asset_bytes
from aiwf_core.core.experiment_records import (
    open_experiment, start_experiment, record_experiment, finish_experiment,
    load_experiment, save_experiment,
)


class TestExperimentAssets(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.TestExperimenterContract()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root

    def start(self, identity):
        open_experiment(str(self.root), identity, "Measure a boundary", task_id="TASK-001")
        return Path(start_experiment(str(self.root), identity)["worktree_path"])

    def freeze(self, identity="EXP-001"):
        worktree = self.start(identity)
        (worktree / "probe.txt").write_text("测量结果\n")
        (worktree / "binary.bin").write_bytes(b"\x00\xff\x01")
        (worktree / "alias").symlink_to("probe.txt")
        (worktree / "app.txt").unlink()
        (worktree / ".gitignore").write_text("private.log\n")
        (worktree / "private.log").write_text("not retained")
        record_experiment(str(worktree), identity, "supported", "Boundary measured",
                          observations=["real boundary result"])
        finish_experiment(str(self.root), identity)
        self.assertFalse(worktree.exists())
        return load_experiment(self.root, identity)

    def test_retained_assets_after_cleanup_do_not_modify_stable_tree(self):
        record = self.freeze()
        before = self.fixture._git("status", "--porcelain")
        assets = experiment_assets(self.root, "EXP-001")
        items = {item["path"]: item for item in assets["assets"]}
        self.assertTrue(items["probe.txt"]["available"])
        self.assertFalse(items["app.txt"]["available"])
        self.assertNotIn("private.log", items)
        self.assertEqual(experiment_asset_bytes(self.root, "EXP-001", "binary.bin"), b"\x00\xff\x01")
        self.assertEqual(experiment_asset_bytes(self.root, "EXP-001", "alias"), b"probe.txt")
        self.assertEqual(experiment_assets(self.root, "EXP-001", "probe.txt")["asset"]["content"], "测量结果\n")
        self.assertEqual(before, self.fixture._git("status", "--porcelain"))
        self.assertEqual(record, load_experiment(self.root, "EXP-001"))
        self.assertEqual((self.root / "app.txt").read_text(), "stable\n")

    def test_missing_snapshot_and_invalid_paths_are_rejected(self):
        self.start("EXP-001")
        with self.assertRaises(ValueError):
            experiment_assets(self.root, "EXP-001")
        self.freeze("EXP-002")
        for path in ("../app.txt", "/app.txt", ".aiwf/state/state.json", "private.log", "app.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                experiment_assets(self.root, "EXP-002", path)

    def test_reuse_cites_immutable_source_without_copying_its_conclusion(self):
        source = self.freeze()
        source["status"] = "stale"
        save_experiment(self.root, source)
        worktree = self.start("EXP-002")
        (worktree / "probe.txt").write_bytes(experiment_asset_bytes(self.root, "EXP-001", "probe.txt"))
        recorded = record_experiment(str(worktree), "EXP-002", "inconclusive", "New run blocked",
                                     observations=["new environment unavailable"],
                                     source_experiments=["EXP-001"])
        self.assertEqual(recorded["conclusion"], "inconclusive")
        self.assertEqual(recorded["source_experiments"][0]["experiment_ref"], source["experiment_ref"])
        self.assertEqual(recorded["subject_ref"], self.fixture.origin)
        self.assertEqual(load_experiment(self.root, "EXP-001")["conclusion"], "supported")

    def test_self_or_unrecorded_source_does_not_freeze_new_experiment(self):
        worktree = self.start("EXP-001")
        self.start("EXP-002")
        for source in ("EXP-001", "EXP-002", "EXP-missing"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                record_experiment(str(worktree), "EXP-001", "inconclusive", "Blocked",
                                  observations=["no result"], source_experiments=[source])
            self.assertEqual(load_experiment(self.root, "EXP-001")["status"], "running")

    def test_cli_reads_binary_and_lists_task_owned_assets(self):
        self.freeze()
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
        command = [sys.executable, "-m", "aiwf_core.cli", "experiment", "assets", "EXP-001"]
        result = subprocess.run(command, cwd=self.root, env=env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["scope"], {"kind": "task", "id": "TASK-001"})
        result = subprocess.run(command + ["--path", "binary.bin", "--raw"], cwd=self.root, env=env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"\x00\xff\x01")


if __name__ == "__main__":
    unittest.main()
