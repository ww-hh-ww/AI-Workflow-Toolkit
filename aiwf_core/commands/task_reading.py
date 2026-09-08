"""Read human-facing Task meaning directly from Markdown, without new state."""
import re

from ..core.task_proof import _section, VERIFICATION_LABELS
from ..core.worktree_context import resolve_control_root


def read_task_story(base_dir, task):
    control = resolve_control_root(base_dir)
    path = control / str(task.get("doc_path") or f".aiwf/tasks/{task['id']}.md")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    proof = _section(text, "Proof Standard")
    # Reuse the contract's headings and labels, not a separate summary document.
    labels = "|".join(re.escape(label) for label in VERIFICATION_LABELS)
    done = re.split(rf"(?m)^\s*(?:{labels})\s*[:：]?\s*$", proof, maxsplit=1)[0]
    done = re.sub(r"^\s*(?:Done When|完成条件)\s*[:：]?\s*", "", done).strip()
    def section2(name):
        match = re.search(rf"(?m)^## {re.escape(name)}\s*\n([\s\S]*?)(?=^## |\Z)", text)
        return match.group(1).strip() if match else ""
    return {
        "Intent": _section(text, "Objective"),
        "Scope": _section(text, "Contract Responsibility"),
        "Done when": done,
        "Open questions": section2("Open Judgment"),
        "Actual outcome": section2("Closure Calibration"),
    }


def print_task_story(base_dir, task):
    for label, content in read_task_story(base_dir, task).items():
        if content:
            print(f"  {label}:")
            for line in content.splitlines():
                print(f"    {line}")
