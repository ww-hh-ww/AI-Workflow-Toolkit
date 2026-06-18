"""Claim-Evidence Alignment operations.

Every assertion an agent makes about task completion must be traceable
to machine-observed evidence. Unsupported claims block task close.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _claims_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "records" / "claims.json"


def _read(path: Path, default: Optional[Dict] = None) -> Dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


def _write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_claims(base_dir: str) -> Dict[str, Any]:
    from ..state_schema import default_claims
    claims = _read(_claims_path(base_dir), default_claims())
    if not isinstance(claims.get("claims"), list):
        claims["claims"] = []
    return claims


def save_claims(base_dir: str, claims: Dict[str, Any]) -> None:
    _write(_claims_path(base_dir), claims)


def record_claim(
    base_dir: str,
    text: str,
    task_id: str = "",
    evidence_ids: Optional[List[str]] = None,
    claim_id: str = "",
) -> Dict[str, Any]:
    """Record a claim and link it to evidence. Status starts as pending."""
    claims = load_claims(base_dir)
    evidence_ids = evidence_ids or []

    cid = claim_id or f"CL-{len(claims['claims']) + 1:03d}"
    claim = {
        "id": cid,
        "text": text,
        "task_id": task_id,
        "evidence_ids": evidence_ids,
        "status": "pending",
        "strength": "none",
        "recorded_at": _now(),
        "verified_at": "",
    }
    claims["claims"].append(claim)
    save_claims(base_dir, claims)
    return claim


def verify_claims(base_dir: str, task_id: str = "") -> Dict[str, Any]:
    """Auto-verify claim-evidence alignment for a task.

    For each claim:
    - Look up its evidence_ids in evidence/records.json
    - supported: all evidence exists and is accepted
    - unsupported: no evidence or all evidence rejected
    - overclaimed: evidence exists but is weak (prose-only, single source)
    """
    from ..state_schema import VALID_CLAIM_STATUSES

    claims_data = load_claims(base_dir)
    evidence_path = Path(base_dir) / ".aiwf" / "records" / "evidence.json"
    evidence_data = _read(evidence_path, {"records": []})
    records = evidence_data.get("records", []) or []

    evidence_by_id = {}
    for r in records:
        if isinstance(r, dict) and r.get("id"):
            evidence_by_id[str(r["id"])] = r

    results = []
    unsupported = 0
    overclaimed = 0

    for claim in claims_data.get("claims", []):
        if task_id and claim.get("task_id") != task_id:
            continue

        eids = claim.get("evidence_ids", []) or []
        if not eids:
            claim["status"] = "unsupported"
            claim["strength"] = "none"
            unsupported += 1
            results.append({"claim_id": claim["id"], "status": "unsupported", "reason": "no evidence linked"})
            continue

        matched = [evidence_by_id[eid] for eid in eids if eid in evidence_by_id]
        missing = [eid for eid in eids if eid not in evidence_by_id]

        if not matched:
            claim["status"] = "unsupported"
            claim["strength"] = "none"
            unsupported += 1
            results.append({"claim_id": claim["id"], "status": "unsupported",
                           "reason": f"evidence not found: {', '.join(missing[:3])}"})
            continue

        accepted = [r for r in matched if r.get("status") == "accepted"]
        machine = [r for r in matched if r.get("trust") == "machine_observed"]

        if not accepted:
            claim["status"] = "unsupported"
            claim["strength"] = "weak"
            unsupported += 1
            results.append({"claim_id": claim["id"], "status": "unsupported",
                           "reason": "evidence exists but not accepted"})
        elif len(machine) < len(eids):
            claim["status"] = "overclaimed"
            claim["strength"] = "weak"
            overclaimed += 1
            results.append({"claim_id": claim["id"], "status": "overclaimed",
                           "reason": f"claim broader than evidence: {len(machine)}/{len(eids)} machine-observed"})
        else:
            claim["status"] = "supported"
            claim["strength"] = "strong"
            results.append({"claim_id": claim["id"], "status": "supported",
                           "reason": f"{len(accepted)} accepted evidence, all machine-observed"})

        claim["verified_at"] = _now()

    save_claims(base_dir, claims_data)
    return {
        "results": results,
        "unsupported_count": unsupported,
        "overclaimed_count": overclaimed,
        "total": len(results),
        "all_supported": unsupported == 0 and overclaimed == 0,
    }


def unsupported_claims_blockers(base_dir: str, task_id: str = "") -> List[str]:
    """Return blockers for unsupported/overclaimed claims on a task.

    For L1+: every claim must be supported before task close.
    """
    result = verify_claims(base_dir, task_id=task_id)
    blockers = []
    for r in result["results"]:
        if r["status"] in ("unsupported", "overclaimed"):
            blockers.append(f"Claim {r['claim_id']}: {r['status']} — {r['reason']}")
    return blockers
