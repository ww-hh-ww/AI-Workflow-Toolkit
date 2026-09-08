"""Host-specific prompt vocabulary, shared by installation and live status.

These adapters change tool syntax, never Task authority or acceptance rules.
"""
import re


def _codex_text(text: str) -> str:
    converted = (
        text.replace("Claude Code", "Codex")
        .replace("`EnterWorktree`", "a worktree-switching tool")
        .replace("`isolation: worktree`", "tool-managed worktree isolation")
        .replace("Agent/Task tool", "native subagent tool")
        .replace("Agent call", "subagent call")
    )
    converted = re.sub(r"(?<![A-Za-z0-9_])/(aiwf-[a-z-]+)", r"$\1", converted)
    converted = converted.replace(
        "with `SendMessage`", "by sending one follow-up message to the existing agent thread"
    ).replace(
        "with SendMessage", "by sending one follow-up message to the existing agent thread"
    ).replace("`SendMessage`", "the existing agent thread").replace(
        "## SendMessage", "## Resume an existing agent"
    )
    converted = re.sub(
        r'`Agent\(\{subagent_type: "([^"]+)", prompt: "(.*?)"\}\)`',
        lambda match: (
            f"Dispatch the `{match.group(1)}` custom agent with this message: "
            f"`{match.group(2)}`"
        ),
        converted,
    )
    converted = converted.replace(
        "- Treat the assigned worktree as the project root. AIWF keeps relative file,\n"
        "  search, and Bash tools there. Run `pwd` once; if it is not the assigned path,\n"
        "  return to Planner.",
        "- Treat the assigned worktree as the project root. Codex may still report the\n"
        "  parent session directory inside subagent hooks, so use the exact assigned\n"
        "  worktree path from the dispatch for project reads, writes, and commands. Do\n"
        "  not return merely because `pwd` shows the control root; return only when the\n"
        "  assigned worktree is missing or inaccessible.",
    )
    return converted


def _opencode_text(text: str) -> str:
    converted = (
        text.replace("Claude Code", "OpenCode")
        .replace("`EnterWorktree`", "a worktree-switching tool")
        .replace("`isolation: worktree`", "tool-managed worktree isolation")
        .replace("Follow /aiwf-critic.", "Follow the aiwf-critic role instructions.")
        .replace("Agent({subagent_type:", "task({subagent_type:")
    )
    converted = re.sub(
        r"## SendMessage\n.*?(?=\n## Parallel Plans)",
        """## Continue a child session

Do not start the next Task role while the current child session is running.
When a returned child missed a small, specific item, continue that child once
with `task_id` set to its Task session ID and send only the new finding. If continuation
is unavailable, dispatch a new role with the Task ID and tell it to read
`aiwf task proof`. Do not repeat Task.md.

If the new information changes execution, boundaries, or acceptance, ask the
user to interrupt. Revise and critique the contract before dispatching again.
""".rstrip(),
        converted,
        flags=re.DOTALL,
    )
    converted = (
        converted
        .replace("current session or the resumed original session", "current OpenCode session")
        .replace("resume that Agent", "continue that child")
        .replace("resume that Agent only", "continue that child only")
        .replace("resume is unavailable or fails", "continuation is unavailable")
        .replace("Do not retry the resume", "Do not retry continuation")
        .replace("with `SendMessage`", "through child continuation")
        .replace("with SendMessage", "through child continuation")
        .replace("`SendMessage`", "child continuation")
        .replace("SendMessage", "child continuation")
    )
    converted = converted.replace(
        "Planner does not switch worktrees to manage Task roles. Use the exact Task ID\n"
        "and assigned worktree for every dispatch or Task command. When several Tasks\n"
        "are active, `aiwf status --prompt` shows all Plan worktrees and marks the one\n"
        "matching the current directory.",
        "Keep planning decisions in the control-root Planner session. Dispatch the named\n"
        "OpenCode subagent there with exactly one Task ID. AIWF binds the child session to\n"
        "that Task and routes its project tools to the assigned Plan worktree. Run Executor,\n"
        "Experimenter, and Reviewer in the foreground. Independent Plans may use separate\n"
        "control-root OpenCode sessions when they need to run at the same time.",
    )
    return converted



def host_action(action: str, host: str) -> str:
    if host == "codex":
        action = action.replace("the resumed original Claude session", "a resumed Codex task")
        return _codex_text(action).replace("Claude session", "Codex task")
    if host == "opencode":
        return _opencode_text(action).replace("Claude session", "OpenCode session")
    return action
