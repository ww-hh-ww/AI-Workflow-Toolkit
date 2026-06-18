"""AIWF Quality Surfaces — minimum test/review obligations per change surface type.

workflow_level decides "how deep" to test.
surface_type decides "what failure-mode directions" to test.
These are minimums, not exhaustive scripts. Tester should add task-specific cases.
"""

SURFACE_OBLIGATIONS = {
    # ── Real-world project surfaces ──
    "api_endpoint": {
        "label": "API endpoint",
        "test_obligations": [
            "normal request path",
            "invalid input / missing resource",
            "error status / error body",
            "response schema / contract",
            "route is wired through intended path",
            "auth/middleware if applicable",
        ],
        "review_obligations": [
            "handler/service boundary is clean",
            "route/middleware integration correct",
            "errors consistent with project style",
            "no bypass of auth/validation",
        ],
    },
    "frontend_interaction": {
        "label": "Frontend interaction",
        "test_obligations": [
            "happy user path",
            "loading / error / empty state if relevant",
            "state update after action",
            "repeated or invalid interaction if likely",
            "integration with API/state layer if applicable",
        ],
        "review_obligations": [
            "UI behavior matches user-visible outcome",
            "component/state boundaries respected",
            "no duplicate logic / unnecessary abstraction",
            "accessibility or UX concern noted when relevant",
        ],
    },
    "state_management": {
        "label": "State management",
        "test_obligations": [
            "state transition happy path",
            "invalid/repeated transition if relevant",
            "stale/cache state behavior",
            "no unintended state mutation",
            "integration with UI/API consumer if applicable",
        ],
        "review_obligations": [
            "state ownership clear",
            "no hidden coupling",
            "derived state consistent",
            "no broad state pollution",
        ],
    },
    "persistence": {
        "label": "Persistence",
        "test_obligations": [
            "create/read/update/delete path if relevant",
            "missing record / duplicate / invalid data",
            "transaction/rollback behavior if relevant",
            "persistence boundary covered, not just service mock",
        ],
        "review_obligations": [
            "data model and access boundary clear",
            "migration/schema implications considered",
            "no unsafe data loss",
            "error handling clear",
        ],
    },
    "auth_permission": {
        "label": "Auth/permission",
        "test_obligations": [
            "allowed user path",
            "denied user path",
            "unauthenticated path",
            "privilege boundary",
            "no accidental bypass through alternate route",
        ],
        "review_obligations": [
            "checks happen at correct layer",
            "no trust in client-only state",
            "permissions consistent with project model",
            "sensitive data not exposed",
        ],
    },
    "file_io": {
        "label": "File I/O",
        "test_obligations": [
            "normal file path",
            "missing file / invalid file",
            "permission or malformed input if relevant",
            "output format / path safety",
            "cleanup of temp files if relevant",
        ],
        "review_obligations": [
            "path handling safe",
            "no accidental overwrite",
            "file format assumptions explicit",
            "errors recoverable",
        ],
    },
    "background_job": {
        "label": "Background job",
        "test_obligations": [
            "job scheduled/triggered",
            "success path",
            "failure/retry path",
            "idempotency if relevant",
            "integration with persistence/external service if applicable",
        ],
        "review_obligations": [
            "retry and failure semantics clear",
            "no duplicate side effects",
            "observability/logging sufficient",
            "resource use bounded",
        ],
    },
    "build_config": {
        "label": "Build config",
        "test_obligations": [
            "config parses/build command candidate works or is documented",
            "affected command path identified",
            "invalid/missing dependency risk noted",
            "no unrelated config drift",
        ],
        "review_obligations": [
            "config change scoped",
            "environment assumptions explicit",
            "no hidden dev/prod mismatch",
            "no unrelated toolchain churn",
        ],
    },
    "deployment": {
        "label": "Deployment",
        "test_obligations": [
            "dry-run or static validation if possible",
            "required env/config documented without secrets",
            "rollback/failure path considered",
            "no push/deploy without explicit user authorization",
        ],
        "review_obligations": [
            "deployment boundary clear",
            "secrets not exposed",
            "destructive operations guarded",
            "environment-specific risk noted",
        ],
    },
    "numeric_logic": {
        "label": "Numeric logic",
        "test_obligations": [
            "normal case",
            "boundary values",
            "invalid numeric input",
            "special numeric semantics relevant to language/domain",
            "consistency with existing operations",
        ],
        "review_obligations": [
            "numeric assumptions explicit",
            "error semantics consistent",
            "no hidden type/coercion broadening",
            "precision/overflow/deferred risks noted",
        ],
    },
    "embedded_hardware_io": {
        "label": "Embedded hardware I/O",
        "test_obligations": [
            "init path",
            "read/write success path",
            "hardware unavailable/failure path if simulatable",
            "timing/blocking concern noted",
            "integration with main loop or task scheduler",
        ],
        "review_obligations": [
            "pins/bus/resource conflicts checked",
            "init order correct",
            "blocking/resource use acceptable",
            "hardware failure behavior defined",
        ],
    },
    "timing_concurrency": {
        "label": "Timing/concurrency",
        "test_obligations": [
            "normal async path",
            "race/repeat/cancel/timeout path if relevant",
            "ordering assumption checked",
            "resource cleanup",
        ],
        "review_obligations": [
            "shared state protected",
            "timeout/retry behavior clear",
            "no unbounded loop/wait",
            "failure path observable",
        ],
    },
    "public_api_sdk": {
        "label": "Public API/SDK",
        "test_obligations": [
            "public import/export path",
            "backward compatibility if existing API",
            "invalid input/error contract",
            "documentation or usage example if relevant",
        ],
        "review_obligations": [
            "public surface intentional",
            "no accidental breaking change",
            "naming/semantics consistent",
            "API behavior stable",
        ],
    },
    "data_migration": {
        "label": "Data migration",
        "test_obligations": [
            "forward migration path",
            "empty/partial/invalid existing data if relevant",
            "rollback or recovery note",
            "no destructive action without explicit authorization",
        ],
        "review_obligations": [
            "data loss risk explicit",
            "idempotency considered",
            "Git rollback strategy recommendation",
            "production safety boundary clear",
        ],
    },
    "error_handling": {
        "label": "Error handling",
        "test_obligations": [
            "expected error path",
            "unexpected/malformed input path",
            "user-visible error behavior",
            "no swallowed failure",
        ],
        "review_obligations": [
            "errors are actionable",
            "no false success",
            "logging/propagation appropriate",
            "consistency with project style",
        ],
    },
    # ── AIWF tool surfaces ──
    "state_mutation_cli": {
        "label": "State mutation CLI",
        "test_obligations": [
            "happy path mutates expected state",
            "invalid target / unknown ID fails cleanly",
            "failed command does not mutate state",
            "failed command does not print success",
            "failure returns nonzero or explicit error",
            "user-facing invalid input does not traceback",
        ],
        "review_obligations": [
            "reject if mutation CLI only has happy-path tests",
            "check failed mutation leaves state unchanged",
            "check no false success output",
        ],
    },
    "read_only_cli": {
        "label": "Read-only CLI",
        "test_obligations": [
            "missing file/state handled gracefully",
            "command does not mutate state",
            "no raw JSON dump unless explicitly requested",
            "output is short and human-readable",
            "no traceback for normal missing-state cases",
        ],
        "review_obligations": [
            "check command is truly read-only",
            "check human surface is concise",
        ],
    },
    "report_exporter": {
        "label": "Report exporter",
        "test_obligations": [
            "missing fields tolerated",
            "string/dict/list variants tolerated",
            "no raw JSON dump",
            "important sections present",
            "structured lessons / risks / ACRs do not crash exporter",
        ],
        "review_obligations": [
            "reject if report only works for happy-path schema",
            "check report is human-readable, not JSON mirror",
        ],
    },
    "hook_script": {
        "label": "Hook script",
        "test_obligations": [
            "stdlib-only",
            "fast",
            "no heavy commands",
            "no git/heavy scan unless explicitly allowed",
            "no full JSON dump",
            "no unintended mutation",
            "prompt-cache friendly",
        ],
        "review_obligations": [
            "reject hook changes that increase prompt noise",
            "reject hook changes that do heavy work on every prompt",
        ],
    },
    "state_schema_change": {
        "label": "State schema change",
        "test_obligations": [
            "default fields exist",
            "old files without new fields still work",
            "missing fields fallback safely",
            "report/status do not crash",
            "no raw migration required for ordinary old projects",
        ],
        "review_obligations": [
            "check backward compatibility",
            "check new schema does not force user-visible complexity",
        ],
    },
    "git_command": {
        "label": "Git command safety",
        "test_obligations": [
            "confirm required for destructive operation",
            "no push",
            "no false success on failure",
            "does not drop stash unless explicit",
        ],
        "review_obligations": [
            "reject any automatic commit/push without explicit user confirmation",
            "check failure paths do not destroy state",
        ],
    },
    "memory_retrieval": {
        "label": "Memory retrieval",
        "test_obligations": [
            "relevant items retrieved",
            "unrelated items suppressed",
            "short tokens / stop words do not trigger false positives",
            "dedupe",
            "advisory only",
            "no state mutation",
            "no UserPromptSubmit dump",
        ],
        "review_obligations": [
            "reject retrieval that returns noisy irrelevant memories",
            "reject automatic application of lessons",
        ],
    },
    "environment_scanner": {
        "label": "Environment scanner",
        "test_obligations": [
            "no install",
            "no network",
            "no secret env values",
            "no long commands",
            "only relevant missing tools become risks",
            "command candidates are executable-looking, not script-content concatenations",
        ],
        "review_obligations": [
            "reject false environment risks from unrelated missing tools",
            "check environment profile remains lightweight",
        ],
    },
    "skill_text_change": {
        "label": "Skill text change",
        "test_obligations": [
            "generated skill contains required rule",
            "no contradictory rule",
            "no over-instruction that makes small tasks heavy",
            "no raw internal dump to user",
            "preserves Planner-facing workflow",
        ],
        "review_obligations": [
            "check skill change guides behavior without replacing model judgment",
            "reject excessive rigid checklist bloat",
        ],
    },
}

VALID_SURFACE_TYPES = set(SURFACE_OBLIGATIONS.keys())


def list_surfaces() -> list:
    return sorted(SURFACE_OBLIGATIONS.keys())


def get_surface(name: str) -> dict:
    """Return obligations dict for a named surface, or None if unknown."""
    return SURFACE_OBLIGATIONS.get(name)
