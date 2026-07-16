"""Keep Task writes inside the worktree assigned by AIWF."""
from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _resolve_target(raw_path: str, cwd: Path) -> Optional[Path]:
    value = str(raw_path or "").strip()
    if not value or any(marker in value for marker in ("$", "`")):
        return None
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = cwd / path
        return path.resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def managed_worktrees(control_root: Path) -> List[Path]:
    """Return registered project worktrees, most specific path first."""
    candidates = [control_root.resolve()]
    sources = (
        (control_root / ".aiwf/state/plans.json", "plans", "git_worktree_path"),
        (control_root / ".aiwf/state/tasks.json", "tasks", "worktree_path"),
    )
    for path, collection, field in sources:
        for item in _read_json(path).get(collection, []) or []:
            if not isinstance(item, dict) or not item.get(field):
                continue
            try:
                candidates.append(Path(str(item[field])).expanduser().resolve())
            except (OSError, RuntimeError, ValueError):
                continue

    unique = {str(path): path for path in candidates}
    return sorted(unique.values(), key=lambda path: len(path.parts), reverse=True)


def foreign_worktree_target(
    raw_path: str,
    *,
    cwd: Path,
    control_root: Path,
    assigned_worktree: Path,
) -> Optional[Tuple[Path, Path]]:
    """Return (target, owner) when a write targets another managed worktree."""
    target = _resolve_target(raw_path, cwd)
    if target is None:
        return None
    assigned = assigned_worktree.expanduser().resolve()
    if _is_within(target, assigned):
        return None
    for owner in managed_worktrees(control_root):
        if _is_within(target, owner):
            return target, owner
    return None


def _command_segments(command: str) -> Iterable[List[str]]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return []

    segments: List[List[str]] = []
    current: List[str] = []
    for token in tokens:
        if token in {"|", "||", "&", "&&", ";"}:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _positional(tokens: List[str]) -> List[str]:
    return [token for token in tokens if token and not token.startswith("-")]


def _command_words(segment: List[str], targets: List[str]) -> List[str]:
    words: List[str] = []
    index = 0
    while index < len(segment):
        token = segment[index]
        redirects = {">", ">>", ">|", ">&", "<>", "<", "<<", "<<<", "<&"}
        if token in redirects and index + 1 < len(segment):
            if words and words[-1].isdigit():
                words.pop()
            destination = segment[index + 1]
            if token not in {"<", "<<", "<<<", "<&"} and not destination.isdigit():
                targets.append(destination)
            index += 2
            continue
        words.append(token)
        index += 1
    return words


def _copy_destination(args: List[str]) -> str:
    for index, arg in enumerate(args):
        if arg in {"-t", "--target-directory"} and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith("--target-directory="):
            return arg.split("=", 1)[1]
    positional = _positional(args)
    return positional[-1] if positional else ""


def shell_write_targets(command: str) -> List[str]:
    """Extract explicit destinations from common shell write commands."""
    targets: List[str] = []
    for segment in _command_segments(command):
        words = _command_words(segment, targets)
        if not words:
            continue
        command_name = Path(words[0]).name.lower()
        args = words[1:]
        if command_name in {"cp", "mv", "rsync", "install"}:
            destination = _copy_destination(args)
            if destination:
                targets.append(destination)
        elif command_name in {
            "rm", "unlink", "truncate", "touch", "mkdir", "rmdir", "chmod", "chown",
        }:
            targets.extend(_positional(args))
        elif command_name == "tee":
            targets.extend(_positional(args))
        elif command_name == "dd":
            targets.extend(
                arg[3:] for arg in args if arg.startswith("of=") and len(arg) > 3
            )
        elif command_name == "git" and args:
            git_command = args[0].lower()
            git_args = args[1:]
            if git_command == "mv":
                destination = _copy_destination(git_args)
                if destination:
                    targets.append(destination)
            elif git_command == "rm":
                targets.extend(_positional(git_args))
        elif command_name in {"sed", "perl"} and any(
            arg == "--in-place" or arg.startswith("-i") for arg in args
        ):
            targets.extend(_positional(args))
    return targets


def foreign_bash_write(
    command: str,
    *,
    cwd: Path,
    control_root: Path,
    assigned_worktree: Path,
) -> Optional[Tuple[Path, Path]]:
    for target in shell_write_targets(command):
        violation = foreign_worktree_target(
            target,
            cwd=cwd,
            control_root=control_root,
            assigned_worktree=assigned_worktree,
        )
        if violation:
            return violation
    return None
