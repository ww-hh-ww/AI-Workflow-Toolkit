# AIWF Lesson Admission Policy

Lessons are not general summaries. They must meet admission criteria.

## Admission Rules

A lesson may be recorded only if it meets at least one:
- Future tasks of the same type would reuse it
- It would change planner/tester/reviewer behavior
- It comes from a real bug, review blocker, scope violation, or user decision
- It can be converted into test_focus / review_focus / non_goal / escalation_trigger

## Do NOT record

- "Task completed successfully"
- Vague values ("write better code")
- Facts already expressed in code/tests
- Observations that cannot influence future behavior

## Recommended fields

| Field | Meaning |
|-------|---------|
| lesson | What was learned |
| applies_to | task_type(s) this affects |
| affects | plan | test | review | scope | cleanup | close |
| source | bug | review_blocker | scope_violation | user_decision | field_observation |
| status | active | superseded | resolved_by_code |
| expires_when | condition that makes this obsolete |

## Examples

Good:
- "Scope path normalization: absolute Claude paths must be normalized to project-relative"
  applies_to=all, affects=review+scope, source=bug

- "Prepare_close must promote evidence before checking closure gates"
  applies_to=all, affects=close, source=review_blocker

Bad:
- "We implemented subtract successfully"
- "Tests passed"  
- "Code is clean"
