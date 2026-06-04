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
EXCLUDE_PATTERNS=(
  "__MACOSX"
  ".DS_Store"
  "._*"
  "__pycache__"
  "*.pyc"
  "*.pyo"
  ".pytest_cache"
  ".mypy_cache"
  ".ruff_cache"
  ".venv"
  "venv"
  "build"
  "dist"
  "*.egg-info"
  "AIWF-v*.zip"
)

echo "1. Collecting files..."
find . -type f | while read f; do
  skip=false
  for pat in "${EXCLUDE_PATTERNS[@]}"; do
    if [[ "$f" == *"$pat"* ]]; then
      skip=true; break
    fi
  done
  if [[ "$f" == ./.git/* ]]; then skip=true; fi
  if [[ "$f" == ./.aiwf/* ]]; then skip=true; fi
  if [[ "$f" == ./.claude/* ]]; then skip=true; fi
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

echo "2. Creating zip..."
cd "$ROOT"
zip -q "$WORKDIR/release.zip" -@ < "$WORKDIR/filelist.txt"

echo "3. Auditing zip..."
AUDIT_FAILED=false
unzip -q "$WORKDIR/release.zip" -d "$WORKDIR/unzip"

for pattern in "__MACOSX" ".DS_Store" "._" "settings.local.json"; do
  if unzip -l "$WORKDIR/release.zip" 2>/dev/null | grep -q "$pattern"; then
    echo "   FAIL: Found '$pattern' in zip"
    AUDIT_FAILED=true
  fi
done

if find "$WORKDIR/unzip" \( -path '*/.aiwf/*' -o -path '*/.claude/*' -o -name '.DS_Store' -o -name '._*' \) -print -quit | grep -q .; then
  echo "   FAIL: Found runtime or macOS metadata in zip"
  AUDIT_FAILED=true
fi

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

cp "$WORKDIR/release.zip" "$ROOT/$RELEASE"
echo ""
echo "Release: $ROOT/$RELEASE"
echo "Files:   $FILE_COUNT"
echo "PASSED"
