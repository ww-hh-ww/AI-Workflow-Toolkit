#!/usr/bin/env bash
set -eo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/aiwf-pycache}"

[[ -f "$ROOT/bin/aiwf" ]] && chmod +x "$ROOT/bin/aiwf" 2>/dev/null || true

TIMEOUT_SEC=45

# Each file runs in its own process. If it hangs, it is killed.
# Explicit per-file execution replaces unittest discovery (quarantined due to hangs).
TESTS=(
  "tests/embedded/test_install_contract.py"
  "tests/embedded/test_hooks_contract.py"
  "tests/embedded/test_event_role_provenance.py"
  "tests/embedded/test_governance_files.py"
  "tests/embedded/test_node_link_contract.py"
  "tests/embedded/test_project_root_resolution.py"
  "tests/embedded/test_scope_path_normalization.py"
  "tests/embedded/test_git_task_records.py"
  "tests/embedded/test_task_parallel_contract.py"
  "tests/embedded/test_agent_worktree_routing.py"
  "tests/embedded/test_record_dispatch_contract.py"
  "tests/embedded/test_state_cli_ops.py"
  "tests/embedded/test_task_proof_contract.py"
  "tests/embedded/test_task_close_sync_contract.py"
  "tests/embedded/test_planner_decision_contract.py"
  "tests/embedded/test_planner_first_flow.py"
  "tests/embedded/test_prompt_clarity_contract.py"
  "tests/embedded/test_no_external_orchestration.py"
  "tests/embedded/test_v2_core.py"
)

echo "=== AIWF Embedded Self-Test ==="
echo ""

PASSED=()
FAILED=()
TIMED_OUT=()

for t in "${TESTS[@]}"; do
  echo "--- $t ---"
  cd "$ROOT"

  # Run with explicit timeout via background process + wait
  python3 -u "$ROOT/$t" 2>&1 &
  PID=$!

  # Wait up to TIMEOUT_SEC, kill if still running
  waited=0
  while kill -0 $PID 2>/dev/null && [ $waited -lt $TIMEOUT_SEC ]; do
    sleep 1
    waited=$((waited + 1))
  done

  if kill -0 $PID 2>/dev/null; then
    # Still running — timed out
    kill -9 $PID 2>/dev/null || true
    wait $PID 2>/dev/null || true
    TIMED_OUT+=("$t")
    echo "  TIMED OUT after ${TIMEOUT_SEC}s"
  else
    # Completed — check exit status
    wait $PID 2>/dev/null
    rc=$?
    if [ $rc -eq 0 ]; then
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

if [ ${#FAILED[@]} -gt 0 ] || [ ${#TIMED_OUT[@]} -gt 0 ]; then
  echo ""
  echo "EMBEDDED SELF-TEST FAILED"
  exit 1
fi

echo ""
echo "EMBEDDED SELF-TEST PASSED"
