"""Interactive TUI actions that leave or temporarily replace the main view."""
from __future__ import annotations

import curses
import os
import shlex
import shutil
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def wrap_display_lines(lines: list[str], width: int) -> list[str]:
    """Wrap text by terminal display cells without dropping characters."""
    width = max(1, width)
    wrapped: list[str] = []
    for source in lines:
        if not source:
            wrapped.append("")
            continue
        current: list[str] = []
        current_width = 0
        for char in source.expandtabs(4):
            char_width = _display_width(char)
            if current and current_width + char_width > width:
                wrapped.append("".join(current))
                current = []
                current_width = 0
            current.append(char)
            current_width += char_width
        wrapped.append("".join(current))
    return wrapped


def _draw_wrapped(stdscr, lines: list[str], x: int, width: int, max_rows: int) -> None:
    for index, line in enumerate(wrap_display_lines(lines, width)[:max_rows]):
        try:
            stdscr.addstr(index, x, line)
        except curses.error:
            pass


def memory_paths(root: Path) -> list[Path]:
    memory = root / ".aiwf" / "memory"
    preferred = [memory / "MEMORY.md", memory / "project-facts.md"]
    notes = sorted((memory / "notes").glob("*.md")) if (memory / "notes").exists() else []
    return [path for path in preferred + notes if path.exists()]


def memory_browser(stdscr, root: Path) -> None:
    selected = 0
    while True:
        paths = memory_paths(root)
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        if not paths:
            show_message(stdscr, "Memory", ["没有可读的 Memory 文件。"])
            return
        selected = max(0, min(selected, len(paths) - 1))
        list_w = min(34, max(20, w // 3))
        for index, path in enumerate(paths[:h - 2]):
            label = path.relative_to(root / ".aiwf" / "memory").as_posix()
            attr = curses.A_REVERSE if index == selected else 0
            try:
                stdscr.addstr(index, 0, label[:list_w - 1].ljust(list_w - 1), attr)
            except curses.error:
                pass
        try:
            text = paths[selected].read_text(encoding="utf-8")
        except Exception as exc:
            text = f"无法读取: {exc}"
        preview_width = max(1, w - list_w - 2)
        preview = wrap_display_lines(text.splitlines(), preview_width)
        for index, line in enumerate(preview[:h - 2]):
            try:
                stdscr.addstr(index, list_w + 1, line)
            except curses.error:
                pass
        help_text = "Memory  j/k:选择  Enter/e:编辑  q:返回"
        try:
            stdscr.addstr(h - 1, 0, help_text[:w - 1], curses.A_REVERSE)
        except curses.error:
            pass
        stdscr.refresh()
        key = stdscr.getch()
        if key == ord("q"):
            return
        if key in (ord("j"), curses.KEY_DOWN):
            selected = min(selected + 1, len(paths) - 1)
        elif key in (ord("k"), curses.KEY_UP):
            selected = max(selected - 1, 0)
        elif key in (ord("\n"), ord("e")):
            warning = edit_file(root, paths[selected])
            if warning:
                show_message(stdscr, "编辑器", [warning])


def _run_external(command: list[str], root: Path):
    try:
        curses.def_prog_mode()
    except curses.error:
        pass
    curses.endwin()
    try:
        try:
            return subprocess.run(command, cwd=str(root))
        except OSError:
            return None
    finally:
        try:
            curses.reset_prog_mode()
            curses.curs_set(0)
            curses.doupdate()
        except curses.error:
            pass


@lru_cache(maxsize=8)
def _editor_help(editor: str) -> str:
    try:
        result = subprocess.run(
            [editor, "-h"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout + result.stderr


def editor_command(path: Path) -> tuple[list[str], str]:
    """Build one editor invocation without changing global editor config."""
    raw = (os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano").strip()
    try:
        command = shlex.split(raw) if raw else ["nano"]
    except ValueError:
        command = [raw]
    if not command:
        command = ["nano"]

    warning = ""
    if Path(command[0]).name.lower() in {"nano", "rnano"}:
        help_text = _editor_help(command[0])
        if "softwrap" in help_text:
            if not any(arg in {"--softwrap", "-$"} for arg in command[1:]):
                command.append("--softwrap")
            if "atblanks" in help_text and not any(
                arg in {"--atblanks", "-a"} for arg in command[1:]
            ):
                command.append("--atblanks")
        else:
            warning = (
                "当前 nano 不支持显示级软换行（macOS 系统 nano 实际可能是 Pico）。"
                "可安装 GNU nano：brew install nano；或通过 $VISUAL/$EDITOR 选择其他编辑器。"
            )
    return [*command, str(path)], warning


def edit_file(root: Path, path: Path) -> str:
    command, warning = editor_command(path)
    if _run_external(command, root) is None:
        return f"无法启动编辑器：{command[0]}"
    return warning


def choose_git_graph_view(stdscr):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    lines = [
        "Git 图",
        "",
        "Enter / 1  精简：只看 branch、merge 和分叉关系",
        "2          详细：显示 branch 中的全部正常 commits",
        "",
        "AIWF 内部 snapshot 不在 Git 图中显示。按 q 取消。",
    ]
    _draw_wrapped(stdscr, lines, 1, max(1, w - 2), h - 1)
    stdscr.refresh()
    key = stdscr.getch()
    if key in (ord("\n"), ord("1")):
        return "summary"
    if key == ord("2"):
        return "detailed"
    return ""


def open_git_graph(root: Path, view: str = "summary") -> str:
    tig = shutil.which("tig")
    if not tig:
        return "未找到 tig。macOS 可运行: brew install tig"
    command = [tig, "--branches", "--remotes"]
    if view == "summary":
        command.append("--simplify-by-decoration")
    result = _run_external(command, root)
    if result is None:
        return "无法启动 tig。"
    if result.returncode:
        return f"tig 已退出，状态码 {result.returncode}。"
    return ""


def show_message(stdscr, title: str, lines: list[str]) -> None:
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    content = [title, "", *lines]
    _draw_wrapped(stdscr, content, 1, max(1, w - 2), h - 2)
    try:
        stdscr.addstr(h - 1, 1, "按任意键返回", curses.A_REVERSE)
    except curses.error:
        pass
    stdscr.refresh()
    stdscr.getch()


def confirm_temporary_ai_writes(stdscr) -> bool:
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    lines = [
        "临时 AI 写入",
        "",
        "允许当前 AI 在没有 Task 时直接修改项目文件。",
        "AIWF 状态、记录、受保护配置和危险命令仍受保护。",
        "成功激活 Task 时会自动关闭。",
        "",
        "按 y 开启，其他键取消。",
    ]
    _draw_wrapped(stdscr, lines, 1, max(1, w - 2), h - 1)
    stdscr.refresh()
    return stdscr.getch() in (ord("y"), ord("Y"))


def confirm_fixloop_continue(stdscr, task_id: str, route: str, attempt: int) -> bool:
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    lines = [
        "继续 Fix Loop",
        "",
        f"Task: {task_id}",
        f"当前路线: {route or 'planner'}",
        f"失败轮次: {attempt}",
        "",
        "这只解除 escalation，不会把问题标记为已解决。",
        "继续后，Planner 会按当前路线恢复；当前实现通过测试后才能结束。",
        "按 y 继续，其他键取消。",
    ]
    _draw_wrapped(stdscr, lines, 1, max(1, w - 2), h - 1)
    stdscr.refresh()
    return stdscr.getch() in (ord("y"), ord("Y"))
