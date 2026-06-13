#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
ENGINE="${1:-claude}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/aiwf-real-tester-${ENGINE}-XXXXXX")"
export PYTHONPATH="$ROOT"
export PATH="$ROOT/bin:$PATH"
REAL_TEST_TIMEOUT="${REAL_TEST_TIMEOUT:-180}"

cleanup() {
  if [[ "${KEEP_REAL_TEST_PROJECT:-0}" != "1" ]]; then
    rm -rf "$TMP"
  else
    echo "Kept real-test project: $TMP"
  fi
}
trap cleanup EXIT

run_with_timeout() {
  "$@" &
  local command_pid=$!
  (
    sleep "$REAL_TEST_TIMEOUT"
    kill "$command_pid" 2>/dev/null || true
  ) &
  local watchdog_pid=$!
  local status=0
  wait "$command_pid" || status=$?
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  if [[ "$status" -ne 0 ]]; then
    echo "Real Tester process failed or timed out after ${REAL_TEST_TIMEOUT}s (status=$status)" >&2
    return "$status"
  fi
}

cd "$TMP"
mkdir -p tests .smoke-bin
cat > .smoke-bin/aiwf <<EOF
#!/usr/bin/env bash
PYTHONPATH="$ROOT" exec python3 -m aiwf_core.cli "\$@"
EOF
chmod +x .smoke-bin/aiwf
cat > app.py <<'PY'
import sys

def add(a, b):
    return a + b

if __name__ == "__main__":
    values = [int(value) for value in sys.argv[1:]]
    print(f"sum={add(*values)}")
PY
cat > tests/__init__.py <<'PY'
PY
cat > tests/test_unit.py <<'PY'
import unittest
from app import add

class AddUnitTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
PY
cat > tests/test_cli.py <<'PY'
import subprocess
import sys
import unittest

class AddCliTest(unittest.TestCase):
    def test_cli(self):
        result = subprocess.run(
            [sys.executable, "app.py", "2", "3"],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), "sum=5")
PY
git init -q
git config user.email smoke@example.com
git config user.name "AIWF Smoke"
git add app.py tests
git commit -qm "seed real tester smoke project"

aiwf install "$ENGINE" --force >/dev/null
aiwf state record-quality-policy \
  --task-type small_function --workflow-level L2_standard_team \
  --reason "real tester smoke" >/dev/null
aiwf state record-quality-brief \
  --user-visible-outcome "CLI prints sum=5" \
  --acceptance-criterion "CLI prints sum=5 for 2 and 3" \
  --test-obligation "run focused and complete project tests" \
  --review-obligation "verify CLI behavior" \
  --system-integration-obligation "exercise python3 app.py 2 3" \
  --target-structure "Keep app.py CLI and tests" >/dev/null
aiwf state start-context \
  --context-id CTX-SMOKE --label "Real tester smoke" \
  --allowed-write app.py --allowed-write tests \
  --purpose "Validate Tester behavior" --test-focus "unit, full suite, actual CLI" >/dev/null
aiwf task plan \
  --task-id TASK-SMOKE --title "Real tester smoke" --status ready \
  --allowed-write app.py --allowed-write tests >/dev/null
aiwf state rebuild-current-state >/dev/null
aiwf task activate TASK-SMOKE >/dev/null

PROMPT="Validate this active L2 task as Tester. Run the focused unit test, the complete available project test suite, and the actual CLI entrypoint. Record testing with validation layers, full-suite status, real-usage status, acceptance coverage, and system coverage. For every AIWF CLI command, use .smoke-bin/aiwf so the state is written by the current source under test. Do not edit project files."

if [[ "${REAL_TEST_SETUP_ONLY:-0}" == "1" ]]; then
  echo "Real-test project ready: $TMP"
  trap - EXIT
  exit 0
fi

case "$ENGINE" in
  claude)
    run_with_timeout claude -p --agent aiwf-tester --dangerously-skip-permissions \
      --max-budget-usd "${CLAUDE_REAL_TEST_BUDGET:-1.00}" "$PROMPT"
    ;;
  reasonix)
    echo "Reasonix uses its supported interactive mainline; run this in the TUI:"
    echo "/skill aiwf-test $PROMPT"
    reasonix code .
    ;;
  *)
    echo "Usage: $0 claude|reasonix" >&2
    exit 2
    ;;
esac

python3 - <<'PY'
import json
from pathlib import Path

testing = json.loads(Path(".aiwf/artifacts/quality/testing.json").read_text())
assert testing["status"] in ("adequate", "passed"), testing
assert "targeted" in testing["validation_layers"], testing
assert testing["full_suite_status"] == "passed", testing
assert "full_regression" in testing["validation_layers"], testing
assert testing["real_usage_status"] == "passed", testing
assert "real_usage" in testing["validation_layers"], testing
assert len(testing["commands"]) >= 3, testing
print("real tester smoke ok")
print(json.dumps({
    "commands": testing["commands"],
    "validation_layers": testing["validation_layers"],
    "full_suite_status": testing["full_suite_status"],
    "real_usage_status": testing["real_usage_status"],
}, indent=2))
PY
