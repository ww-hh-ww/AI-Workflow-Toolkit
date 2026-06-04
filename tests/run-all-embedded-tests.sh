#!/usr/bin/env bash
set -eo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/aiwf-pycache"

[[ -f "$ROOT/bin/aiwf" ]] && chmod +x "$ROOT/bin/aiwf" 2>/dev/null || true

TIMEOUT_SEC="${AIWF_TEST_TIMEOUT_SEC:-60}"

TESTS=()
while IFS= read -r test_file; do
  TESTS+=("$test_file")
done <<EOF
$(find "$ROOT/tests/embedded" -maxdepth 1 -type f -name 'test_*.py' | sort)
EOF

echo "=== AIWF All Embedded Tests ==="
echo ""

PASSED=()
FAILED=()
TIMED_OUT=()

for t_abs in "${TESTS[@]}"; do
  t="${t_abs#$ROOT/}"
  echo "--- $t ---"
  cd "$ROOT"

  python3 -u "$t_abs" 2>&1 &
  PID=$!

  waited=0
  while kill -0 "$PID" 2>/dev/null && [ "$waited" -lt "$TIMEOUT_SEC" ]; do
    sleep 1
    waited=$((waited + 1))
  done

  if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
    TIMED_OUT+=("$t")
    echo "  TIMED OUT after ${TIMEOUT_SEC}s"
  else
    wait "$PID" 2>/dev/null
    rc=$?
    if [ "$rc" -eq 0 ]; then
      PASSED+=("$t")
      echo "  PASS"
    else
      FAILED+=("$t (exit $rc)")
      echo "  FAIL (exit $rc)"
    fi
  fi
done

echo ""
echo "=========="
echo "Results: ${#PASSED[@]} passed, ${#FAILED[@]} failed, ${#TIMED_OUT[@]} timed out"
for t in "${PASSED[@]}";   do echo "  ✓ $t"; done
for t in "${FAILED[@]}";   do echo "  ✗ $t"; done
for t in "${TIMED_OUT[@]}"; do echo "  ⏰ $t"; done

if [ "${#FAILED[@]}" -gt 0 ] || [ "${#TIMED_OUT[@]}" -gt 0 ]; then
  echo ""
  echo "ALL EMBEDDED TESTS FAILED"
  exit 1
fi

echo ""
echo "ALL EMBEDDED TESTS PASSED"
