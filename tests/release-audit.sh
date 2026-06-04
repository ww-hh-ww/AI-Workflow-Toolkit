#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1

"$ROOT/bin/aiwf" --version | grep -q 'AIWF V1.0'
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/aiwf-pycache}" python3 -m compileall -q "$ROOT/aiwf_core"

test -f "$ROOT/README.md"
test -f "$ROOT/CHANGELOG.md"
test -f "$ROOT/LICENSE"
test -f "$ROOT/pyproject.toml"
test ! -f "$ROOT/V45.6-CHANGELOG.md"
test -x "$ROOT/bin/aiwf"
test ! -d "$ROOT/.ai-workflow"
test -f "$ROOT/docs/AIWF-TECHNICAL-REPORT.md"

git -C "$ROOT" ls-files | grep -E '(^|/)\.DS_Store$|^\._' && {
  echo "tracked macOS metadata found" >&2
  exit 1
} || true

git -C "$ROOT" ls-files | grep -E '^\.aiwf/|^\.claude/|^\.reasonix/' && {
  echo "tracked installed runtime state found" >&2
  exit 1
} || true

grep -R -I -E "V45[.]3|v45[.]3|V45[.]4|v45[.]4|V45[.]5|v45[.]5|V45[.]6|v45[.]6" "$ROOT" \
  --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=__MACOSX \
  --exclude='*.pyc' --exclude='._*' --exclude='*.zip' --exclude=release-audit.sh && {
  echo "stale previous-version reference found" >&2
  exit 1
} || true

grep -R "aiwf_v45_core[.]py" "$ROOT" --exclude=release-audit.sh --exclude=v45-modular-boundary-contract.sh && {
  echo "stale monolith reference found" >&2
  exit 1
} || true

find "$ROOT" \( -name __MACOSX -o -name '._*' \) -print -quit | grep -q . && {
  echo "macOS metadata found in release tree" >&2
  exit 1
} || true

find "$ROOT" \( -path "$ROOT/.git" -o -path "$ROOT/.git/*" \) -prune -o -name '.DS_Store' -print -quit | grep -q . && {
  echo ".DS_Store found in release tree" >&2
  exit 1
} || true

LOCAL_OR_CREDENTIAL_RE='/(Users/wzx|var/folders/)|BE(GIN) (RSA|OPENSSH|PRIVATE)'
grep -R -I -E "$LOCAL_OR_CREDENTIAL_RE" "$ROOT" \
  --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=__MACOSX \
  --exclude='*.pyc' --exclude='._*' --exclude='*.zip' && {
  echo "local path or secret-like content found" >&2
  exit 1
} || true

find "$ROOT" -maxdepth 1 -type f \( -name '*.zip' -o -name '*.tar' -o -name '*.tar.gz' -o -name '*.tgz' \) | while read -r archive; do
  case "$archive" in
    *.zip)
      zipinfo -1 "$archive" | grep -E '(^|/)__MACOSX(/|$)|(^|/)\._' && {
        echo "macOS metadata found in archive: $archive" >&2
        exit 1
      } || true
      ;;
    *.tar|*.tar.gz|*.tgz)
      tar -tf "$archive" | grep -E '(^|/)__MACOSX(/|$)|(^|/)\._' && {
        echo "macOS metadata found in archive: $archive" >&2
        exit 1
      } || true
      ;;
  esac
done

TMP="$(mktemp -d "${TMPDIR:-/tmp}/aiwf-embedded-release-audit-XXXXXX")"
(
  cd "$TMP"
  PYTHONPATH="$ROOT" "$ROOT/bin/aiwf" install reasonix >/dev/null
  test ! -d .ai-workflow
  test -f .aiwf/state/state.json
  test -f .aiwf/state/goal.json
  test -f .aiwf/state/contexts.json
  test -f .aiwf/evidence/records.json
  test -f .aiwf/quality/testing.json
  test -f .aiwf/quality/review.json
  test -f .aiwf/state/fix-loop.json
  test ! -f .aiwf/state.json
  test ! -f .aiwf/review.json
  test -f .reasonix/settings.json
  test -f .reasonix/skills/aiwf-planner/SKILL.md
  test -f .reasonix/skills/aiwf-implement/SKILL.md
  grep -q "Subagent Connection Recovery" .reasonix/skills/aiwf-planner/SKILL.md
  test ! -f .reasonix/agents/aiwf-executor.md
  test -x scripts/aiwf_status.py
  PYTHONPATH="$ROOT" "$ROOT/bin/aiwf" status | grep -q "Embedded Reasonix"
  env -u PYTHONPATH python3 scripts/aiwf_scope_check.py <<'JSON' >/dev/null
{"tool_name":"Write","tool_input":{"file_path":"README.md"}}
JSON
)

TMP_CLAUDE="$(mktemp -d "${TMPDIR:-/tmp}/aiwf-embedded-claude-audit-XXXXXX")"
(
  cd "$TMP_CLAUDE"
  PYTHONPATH="$ROOT" "$ROOT/bin/aiwf" install claude >/dev/null
  test -f .claude/settings.json
  test -f .claude/skills/aiwf-planner/SKILL.md
  test -f .claude/agents/aiwf-executor.md
  grep -q "Subagent Connection Recovery" .claude/skills/aiwf-planner/SKILL.md
  PYTHONPATH="$ROOT" "$ROOT/bin/aiwf" doctor | grep -q "All checks passed"
)

echo "release audit ok"
