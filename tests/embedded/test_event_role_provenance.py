"""Hook payload normalization preserves subagent role provenance."""
import unittest


class TestEventRoleProvenance(unittest.TestCase):
    def test_claude_agent_type_is_preserved(self):
        from aiwf_core.adapters.claude.normalize_event import normalize
        event = normalize({
            "hook_event_name": "PostToolUse",
            "session_id": "session-1",
            "agent_id": "agent-1",
            "agent_type": "tester",
            "transcript_path": "/tmp/session.jsonl",
        })
        self.assertEqual(event.engine, "claude")
        self.assertEqual(event.agent_type, "tester")
        self.assertEqual(event.transcript_path, "/tmp/session.jsonl")

    def test_reasonix_agent_type_is_preserved(self):
        from aiwf_core.adapters.claude.normalize_event import normalize
        event = normalize({
            "event": "PostToolUse",
            "sessionId": "session-2",
            "agentId": "agent-2",
            "agentType": "reviewer",
        })
        self.assertEqual(event.engine, "reasonix")
        self.assertEqual(event.agent_type, "reviewer")


if __name__ == "__main__":
    unittest.main()
