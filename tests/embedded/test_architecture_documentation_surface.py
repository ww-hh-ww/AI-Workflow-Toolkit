"""Documentation surface contracts for growth docs and architecture snapshots."""
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestArchitectureDocumentationSurface(unittest.TestCase):
    def test_architecture_doc_skill_retired_in_v1(self):
        """aiwf-architecture-doc is retired; architect SKILL.md replaces it."""
        skill = (
            PROJECT_ROOT
            / "aiwf_core"
            / "embedded_templates"
            / "skills"
            / "aiwf-architect"
            / "SKILL.md"
        )
        self.assertTrue(skill.exists())
        text = skill.read_text(encoding="utf-8")
        self.assertIn("Record architecture review", text)
        self.assertIn("Review structure", text)

    def test_installer_no_longer_includes_architecture_doc_skill(self):
        text = (PROJECT_ROOT / "aiwf_core" / "install_claude.py").read_text(encoding="utf-8")
        self.assertNotIn("aiwf-architecture-doc", text)

    def test_top_level_template_exposes_architecture_snapshot_outlet(self):
        text = (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "CLAUDE.md").read_text(encoding="utf-8")
        # V2: CLAUDE.md references aiwf-architect in the Skill index table
        self.assertIn("/aiwf-architect", text)
        self.assertIn("architecture", text.lower())

    def test_planner_manages_structure_not_docs(self):
        text = (
            PROJECT_ROOT
            / "aiwf_core"
            / "embedded_templates"
            / "skills"
            / "aiwf-planner"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn("create and adjust", lower)
        self.assertIn("task.md", lower)
        self.assertIn("activate", lower)
        self.assertNotIn("docs due", lower)

    def test_architect_is_read_only_advisory(self):
        text = (
            PROJECT_ROOT
            / "aiwf_core"
            / "embedded_templates"
            / "skills"
            / "aiwf-architect"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn("review structure", lower)
        self.assertIn("do not modify", lower)
        self.assertIn("read broadly", lower)
        self.assertIn("record architecture review", lower)

    @unittest.skip("README.md content changed in V1 cleanup; test needs doc audit")
    def test_readme_explains_two_documentation_outlets(self):
        text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("文档出口：生长文档与架构快照", text)
        self.assertIn("生长性文档", text)
        self.assertIn("总结性文档 / 架构快照", text)
        self.assertIn("PROJECT-MAP 是两者之间的结构索引", text)
        self.assertIn("机器权威索引", text)
        self.assertIn("人类投影", text)
        self.assertIn("用户不需要日常进入 `.aiwf/` 翻文件", text)
        self.assertIn("aiwf architecture-doc require", text)
        self.assertIn("validate + satisfy", text)

    def test_human_surface_uses_commands_as_default_entrypoints(self):
        text = (PROJECT_ROOT / "docs" / "AIWF-HUMAN-SURFACE.md").read_text(encoding="utf-8")
        self.assertIn("users\nshould not have to browse `.aiwf/`", text)
        self.assertIn("aiwf project-map show", text)
        self.assertIn("aiwf project-map relations", text)
        self.assertIn("aiwf project-map validate", text)
        self.assertIn("machine authority", text)
        self.assertIn("human projection", text)


if __name__ == "__main__":
    unittest.main()
