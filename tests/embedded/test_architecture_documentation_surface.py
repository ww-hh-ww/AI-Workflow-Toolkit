"""Documentation surface contracts for growth docs and architecture snapshots."""
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestArchitectureDocumentationSurface(unittest.TestCase):
    def test_architecture_doc_skill_exists_and_defines_snapshot_output(self):
        skill = (
            PROJECT_ROOT
            / "aiwf_core"
            / "embedded_templates"
            / "skills"
            / "aiwf-architecture-doc"
            / "SKILL.md"
        )
        self.assertTrue(skill.exists())
        text = skill.read_text(encoding="utf-8")
        self.assertIn("Architecture snapshot", text)
        self.assertIn(".aiwf/artifacts/reports/架构详细设计.md", text)
        self.assertIn("Growth documentation", text)
        self.assertIn("Evidence Manifest", text)
        self.assertIn("aiwf architecture-doc require", text)
        self.assertIn("aiwf architecture-doc validate", text)
        self.assertIn("aiwf architecture-doc satisfy", text)

    def test_installer_and_doctor_include_architecture_doc_skill(self):
        text = (PROJECT_ROOT / "aiwf_core" / "install_claude.py").read_text(encoding="utf-8")
        self.assertIn('"aiwf-architecture-doc": "skills/aiwf-architecture-doc/SKILL.md"', text)
        self.assertIn('"aiwf-architecture-doc"', text)

    def test_top_level_template_exposes_architecture_snapshot_outlet(self):
        text = (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("architecture snapshot", text)
        self.assertIn("/aiwf-architecture-doc", text)

    def test_planner_routes_docs_to_growth_or_snapshot(self):
        text = (
            PROJECT_ROOT
            / "aiwf_core"
            / "embedded_templates"
            / "skills"
            / "aiwf-planner"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Growth docs", text)
        self.assertIn("/aiwf-planner-docs", text)
        self.assertIn("/aiwf-architecture-doc", text)
        self.assertIn("架构详细设计.md", text)
        self.assertIn("aiwf architecture-doc require", text)
        self.assertIn("aiwf architecture-doc satisfy", text)
        self.assertIn("machine index", text)
        self.assertIn("human projection", text)
        self.assertIn("Users should not need to browse `.aiwf/` directly", text)

    def test_architect_can_recommend_snapshot_without_forcing_every_review(self):
        text = (
            PROJECT_ROOT
            / "aiwf_core"
            / "embedded_templates"
            / "skills"
            / "aiwf-architect"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Architecture Snapshot Trigger", text)
        self.assertIn("/aiwf-architecture-doc", text)
        self.assertIn("Do not generate a snapshot for every architecture review", text)

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
