#!/usr/bin/env bash
set -eo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VERSION="1.0"
RELEASE="AIWF-v${VERSION}-$(date +%Y%m%d).zip"
WORKDIR=$(mktemp -d)
trap "rm -rf '$WORKDIR'" EXIT

echo "=== AIWF Release Builder ==="
echo "Version: $VERSION"
echo "Output: $RELEASE"
echo ""

# Build file list, excluding junk
cd "$ROOT"
EXCLUDE_SUBSTR=(
  "__MACOSX"
  ".DS_Store"
  "._"
  "__pycache__"
  ".pyc"
  ".pyo"
  ".pytest_cache"
  ".mypy_cache"
  ".ruff_cache"
  ".venv"
  "venv"
  "build"
  "dist"
  "AIWF-v"
)
EXCLUDE_PREFIX=(
  "./.git/"
  "./.aiwf/"
  "./.claude/"
  "./scripts/"
  "./.eggs/"
  "./.tox/"
)
EXCLUDE_EXACT=(
  "./aiwf.egg-info/PKG-INFO"
  "./aiwf.egg-info/SOURCES.txt"
  "./aiwf.egg-info/dependency_links.txt"
  "./aiwf.egg-info/entry_points.txt"
  "./aiwf.egg-info/top_level.txt"
)

echo "1. Collecting files..."
find . -type f | while read f; do
  skip=false
  # Substring exclusions
  for pat in "${EXCLUDE_SUBSTR[@]}"; do
    if [[ "$f" == *"$pat"* ]]; then
      skip=true; break
    fi
  done
  # Prefix exclusions
  for prefix in "${EXCLUDE_PREFIX[@]}"; do
    if [[ "$f" == "$prefix"* ]]; then
      skip=true; break
    fi
  done
  # Exact exclusions
  for exact in "${EXCLUDE_EXACT[@]}"; do
    if [[ "$f" == "$exact" ]]; then
      skip=true; break
    fi
  done
  if $skip; then continue; fi
  echo "$f"
done | sort > "$WORKDIR/filelist.txt"

FILE_COUNT=$(wc -l < "$WORKDIR/filelist.txt")
echo "   $FILE_COUNT files collected"

for required in README.md CHANGELOG.md LICENSE pyproject.toml bin/aiwf aiwf_core/cli.py; do
  if ! grep -qx "./$required" "$WORKDIR/filelist.txt"; then
    echo "   FAIL: Missing required release file: $required"
    exit 1
  fi
done

# Pre-audit: verify no root scripts/ slipped in
if grep -q '^\./scripts/' "$WORKDIR/filelist.txt"; then
  echo "   FAIL: Root scripts/ found in file list (must use aiwf_core/embedded_templates/scripts/)"
  exit 1
fi
if grep -q '^\./aiwf\.egg-info/' "$WORKDIR/filelist.txt"; then
  echo "   FAIL: aiwf.egg-info/ found in file list"
  exit 1
fi

echo "2. Creating zip..."
cd "$ROOT"
zip -q "$WORKDIR/release.zip" -@ < "$WORKDIR/filelist.txt"

echo "3. Auditing zip..."
AUDIT_FAILED=false

# Check for forbidden patterns in zip
for pattern in "__MACOSX" ".DS_Store" "._" "settings.local.json"; do
  if unzip -l "$WORKDIR/release.zip" 2>/dev/null | grep -q "$pattern"; then
    echo "   FAIL: Found '$pattern' in zip"
    AUDIT_FAILED=true
  fi
done

# Unzip and check structure
unzip -q "$WORKDIR/release.zip" -d "$WORKDIR/unzip"

# No runtime or metadata dirs
if find "$WORKDIR/unzip" \( -path '*/.aiwf/*' -o -path '*/.claude/*' -o -name '.DS_Store' -o -name '._*' \) -print -quit | grep -q .; then
  echo "   FAIL: Found runtime or macOS metadata in zip"
  AUDIT_FAILED=true
fi

# No root scripts/ directory (must only be in aiwf_core/embedded_templates/scripts/)
if [ -d "$WORKDIR/unzip/scripts" ]; then
  echo "   FAIL: Root scripts/ directory found in zip (belongs in aiwf_core/embedded_templates/scripts/)"
  AUDIT_FAILED=true
fi

# No egg-info directories
if find "$WORKDIR/unzip" -name '*.egg-info' -type d -print -quit | grep -q .; then
  echo "   FAIL: egg-info directory found in zip"
  AUDIT_FAILED=true
fi

# Dual-source check: root scripts/ and embedded scripts/ must not BOTH exist
if [ -d "$WORKDIR/unzip/scripts" ] && [ -d "$WORKDIR/unzip/aiwf_core/embedded_templates/scripts" ]; then
  echo "   FAIL: Both root scripts/ and aiwf_core/embedded_templates/scripts/ exist (dual-source drift)"
  AUDIT_FAILED=true
fi

# No local paths or credentials
LOCAL_OR_CREDENTIAL_RE='/(Users/wzx|private/tmp|var/folders)|BE(GIN) (RSA|OPENSSH|PRIVATE)'
if grep -R -I -E "$LOCAL_OR_CREDENTIAL_RE" "$WORKDIR/unzip" >/dev/null; then
  echo "   FAIL: Found local path or secret-like content in zip"
  AUDIT_FAILED=true
fi

if $AUDIT_FAILED; then
  echo ""
  echo "RELEASE AUDIT FAILED"
  exit 1
fi

echo "   Audit passed"

echo "4. Second-opinion audit (aiwf audit-archive)..."
PYTHONPATH="$ROOT" python3 -m aiwf_core.cli audit-archive "$WORKDIR/release.zip" || {
  echo ""
  echo "RELEASE AUDIT FAILED (aiwf audit-archive)"
  exit 1
}

cp "$WORKDIR/release.zip" "$ROOT/$RELEASE"
echo ""
echo "Release: $ROOT/$RELEASE"
echo "Files:   $FILE_COUNT"
echo "PASSED"
echo ""
echo "Distribute this file: $RELEASE"
echo "  Do NOT repackage or extract-and-rezip — use the exact file."
echo "  Verify any downloaded copy with: aiwf audit-archive <zip>"
