"""Advisory lesson retrieval — keyword matching, no RAG, no auto-apply."""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List, Optional

STOP_WORDS = {"add", "use", "make", "do", "the", "a", "an", "to", "of", "in", "on",
              "for", "with", "and", "or", "is", "are", "be", "this", "that", "it",
              "at", "by", "from", "not", "but", "has", "have", "was", "will", "can"}

def _extract_keywords(goal, task_type, files):
    kws = set()
    for w in re.findall(r'\w+', goal.lower()):
        if len(w) >= 3 and w not in STOP_WORDS: kws.add(w)
    if task_type: kws.add(task_type.lower())
    for f in (files or []):
        for w in re.findall(r'\w+', Path(f).stem.lower()):
            if len(w) >= 3 and w not in STOP_WORDS: kws.add(w)
    return list(kws)

def _rj(path, default=None):
    try: return json.loads(path.read_text()) if path.exists() else (default or {})
    except: return default or {}

def _score(text: str, keywords: List[str]) -> int:
    t = text.lower()
    s = 0
    for k in keywords:
        kl = k.lower()
        if kl in t: s += 1
        elif len(kl) >= 4 and kl[:4] in t: s += 1  # prefix match for stemming
    return s

def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _dedup(items: list, limit: int) -> list:
    seen = set(); result = []
    for item in items:
        n = _normalize(item)
        if n not in seen: seen.add(n); result.append(item)
        if len(result) >= limit: break
    return result


def suggest_relevant_lessons(
    project_root: str, goal: str = "", task_type: str = "",
    files: Optional[List[str]] = None, limit: int = 5,
) -> Dict[str, Any]:
    root = Path(project_root)
    review = _rj(root / ".aiwf" / "artifacts" / "quality" / "review.json")

    # Collect deferred risks from review.json
    drisks_raw = []
    for obs in (review.get("adversarial_observations", []) or []):
        if isinstance(obs, dict) and obs.get("kind") in ("deferred_risk", "architecture_drift", "testing_debt"):
            drisks_raw.append(obs.get("message", ""))

    # Build filtered keywords (min length 3, no stop words)
    keywords = _extract_keywords(goal, task_type, files)

    # Collect lessons from review.json
    all_lessons = []
    for l in review.get("lessons", []) or []:
        text = str(l.get("lesson", l)) if isinstance(l, dict) else str(l)
        applies = str(l.get("applies_to", [])) if isinstance(l, dict) else ""
        all_lessons.append((text, applies, l if isinstance(l, dict) else {}))
    neg = review.get("negative_patterns", []) or []
    fups = review.get("followups", []) or []

    # Score and build suggested uses from affects
    scored_lessons = []
    suggested_test = []
    suggested_review = []
    suggested_non_goals = []
    suggested_escalation = []

    for text, applies, meta in all_lessons:
        # Score: keyword match in text + bonus if applies_to matches task_type
        s = _score(text + " " + applies, keywords)
        if task_type and task_type.lower() in applies.lower(): s += 2
        if s > 0:
            scored_lessons.append((s, text))
            affects = meta.get("affects", []) if isinstance(meta, dict) else []
            if isinstance(affects, str): affects = [affects]
            for a in affects:
                a_lower = a.lower().replace(" ", "_")
                if "test_focus" in a_lower: suggested_test.append(text)
                elif "review_focus" in a_lower: suggested_review.append(text)
                elif "non_goal" in a_lower: suggested_non_goals.append(text)
                elif "escalation" in a_lower: suggested_escalation.append(text)

    scored_neg = []
    for n_text in neg:
        text = str(n_text) if isinstance(n_text, str) else str(n_text.get("lesson", n_text))
        s = _score(text, keywords)
        if s > 0: scored_neg.append((s, text))

    scored_fup = []
    for f_text in fups:
        text = str(f_text) if isinstance(f_text, str) else str(f_text.get("lesson", f_text))
        s = _score(text, keywords)
        if s > 0: scored_fup.append((s, text))

    scored_lessons.sort(key=lambda x: -x[0])
    scored_neg.sort(key=lambda x: -x[0])
    scored_fup.sort(key=lambda x: -x[0])

    # Score deferred risks
    scored_drisks = []
    for r in drisks_raw:
        s = _score(r, keywords)
        if s > 0: scored_drisks.append((s, r))
        # Also generate suggested uses
        if s > 0:
            suggested_review.append(f"Review deferred risk: {r}")
            suggested_escalation.append(f"Escalate if deferred risk becomes in-scope: {r}")
    scored_drisks.sort(key=lambda x: -x[0])

    return {
        "schema_version": 1,
        "relevant_lessons": _dedup([t for _, t in scored_lessons], limit),
        "relevant_negative_patterns": _dedup([t for _, t in scored_neg], limit),
        "followup_candidates": _dedup([t for _, t in scored_fup], limit),
        "relevant_deferred_risks": _dedup([t for _, t in scored_drisks], limit),
        "suggested_test_focus": _dedup(suggested_test, limit),
        "suggested_review_focus": _dedup(suggested_review, limit),
        "suggested_non_goals": _dedup(suggested_non_goals, limit),
        "suggested_escalation_triggers": _dedup(suggested_escalation, limit),
    }
