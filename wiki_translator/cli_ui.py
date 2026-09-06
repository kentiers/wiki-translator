"""
Console UI and Environment Helpers for Wiki Translator Suite.

Provides both modern, beautiful, minimalist Rich TUI components
(rounded boxes, subtle muted badges, styled tables, keyboard palettes)
and legacy clean ASCII fallbacks for non-interactive / test environments.

Toggle via:
  WIKI_TRANSLATOR_UI=rich   -> Force Rich modern UI
  WIKI_TRANSLATOR_UI=plain  -> Force classic ASCII UI
  Default                   -> Auto-detect TTY interactivity & NO_COLOR
"""

import os
from pathlib import Path
import re
import sys
from typing import Any, List, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def is_rich_enabled() -> bool:
    """Determines whether the modern Rich UI should be rendered."""
    if not RICH_AVAILABLE:
        return False

    env_val = os.environ.get("WIKI_TRANSLATOR_UI", "").lower().strip()
    if env_val in ("plain", "legacy", "false", "0"):
        return False
    if env_val in ("rich", "true", "1"):
        return True

    # Check for NO_COLOR standard
    if os.environ.get("NO_COLOR") is not None:
        return False

    # Auto-detect: enable for interactive TTY terminals
    return sys.stdout.isatty()


# Singleton Rich console instance
_console: Optional[Any] = None


def get_console() -> Any:
    """Returns the shared Rich Console instance."""
    global _console
    if _console is None and RICH_AVAILABLE:
        _console = Console(highlight=False, soft_wrap=True)
    return _console


def print_console_safe(text: str) -> None:
    """Print text even when a legacy Windows console cannot encode every glyph."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding))


def print_banner(model: Optional[str] = None, topic: Optional[str] = None) -> None:
    """Prints the official Wiki Translator Suite CLI banner."""
    if is_rich_enabled():
        console = get_console()
        content = Text()
        content.append("en.wikipedia ", style="bold white")
        content.append("➔", style="bold cyan")
        content.append(" id.wikipedia\n", style="bold white")
        if model or topic:
            content.append("Model: ", style="dim")
            content.append(str(model or "default"), style="cyan")
            if topic:
                content.append("  •  Topic: ", style="dim")
                content.append(str(topic), style="cyan")
        else:
            content.append("Powered by Google Antigravity & Gemini LLM", style="dim")
        panel = Panel(
            content,
            title="[bold cyan]🌐 Wiki Translator Suite[/] [dim](Grade A++)[/]",
            title_align="left",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(0, 2),
        )
        console.print(panel)
    else:
        print_console_safe("=" * 72)
        print_console_safe("   🌐 Wikipedia Grade A++ Translator (en.wikipedia -> id.wikipedia)")
        print_console_safe("   Powered by Google Antigravity & Gemini High-Precision LLM")
        print_console_safe("=" * 72)


def render_sections_table(sections: List[Any]) -> None:
    """Renders the section breakdown table."""
    if is_rich_enabled():
        console = get_console()
        table = Table(
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="dim",
            padding=(0, 1),
            show_lines=False,
        )
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("Level", justify="center", width=7)
        table.add_column("Words", justify="right", width=8)
        table.add_column("Chars", justify="right", width=9)
        table.add_column("Section Title", justify="left", style="white")

        for s in sections:
            lvl_badge = f"H{s.level}" if s.level > 1 else "Lead"
            lvl_style = "cyan" if s.level == 1 else "dim"
            table.add_row(
                str(s.index),
                f"[{lvl_style}]{lvl_badge}[/]",
                f"{s.word_count:,}",
                f"{s.char_count:,}",
                s.title,
            )
        console.print(table)
    else:
        print_console_safe("-" * 72)
        print_console_safe(f"{'#':<4} {'Level':<6} {'Words':<8} {'Chars':<8} {'Section Title'}")
        print_console_safe("-" * 72)
        for s in sections:
            print_console_safe(f"{s.index:<4} {s.level:<6} {s.word_count:<8} {s.char_count:<8} {s.title}")
        print_console_safe("-" * 72)


def render_section_header(section_index: int, total_sections: int, title: str, words: int, chars: int) -> None:
    """Renders the banner when starting a new section."""
    if is_rich_enabled():
        console = get_console()
        text = Text()
        text.append(f"Words: {words:,}  •  Chars: {chars:,}", style="dim")
        panel = Panel(
            text,
            title=f"[bold cyan]Section [{section_index}/{total_sections}]:[/] [bold white]{title}[/]",
            title_align="left",
            border_style="blue",
            box=box.ROUNDED,
            padding=(0, 2),
        )
        console.print()
        console.print(panel)
    else:
        print_console_safe(f"\n" + "=" * 72)
        print_console_safe(f"[*] Processing Section [{section_index}/{total_sections}]: {title}")
        print_console_safe(f"    Words: {words} | Chars: {chars}")
        print_console_safe("=" * 72)


def render_review_menu(section_title: str) -> None:
    """Renders the interactive section review keyboard shortcut palette."""
    if is_rich_enabled():
        console = get_console()
        menu_text = Text()
        menu_text.append("[A]", style="bold green")
        menu_text.append(" Approve     ", style="white")
        menu_text.append("[D]", style="bold cyan")
        menu_text.append(" Diff        ", style="white")
        menu_text.append("[V]", style="bold cyan")
        menu_text.append(" Preview     ", style="white")
        menu_text.append("[F]", style="bold yellow")
        menu_text.append(" Auto-Fix\n", style="white")

        menu_text.append("[P]", style="bold magenta")
        menu_text.append(" Polish      ", style="white")
        menu_text.append("[R]", style="bold yellow")
        menu_text.append(" Regenerate  ", style="white")
        menu_text.append("[E]", style="bold cyan")
        menu_text.append(" Note Context", style="white")
        menu_text.append(" [S]", style="bold dim")
        menu_text.append(" Skip  ", style="white")
        menu_text.append("[Q]", style="bold red")
        menu_text.append(" Save & Quit", style="white")

        panel = Panel(
            menu_text,
            title=f"[bold]Review:[/] [dim]{section_title}[/]",
            title_align="left",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        console.print()
        console.print(panel)
    else:
        print_console_safe("\n[?] Review Section Translation:")
        print_console_safe("  [A] Approve & Continue")
        print_console_safe("  [D] Diff / Side-by-side comparison (Source EN vs Draft ID)")
        print_console_safe("  [V] View in Browser (HTML Preview)")
        print_console_safe("  [F] Auto-fix Slop & Syntax Balancer")
        print_console_safe("  [P] Polish / Humanize (Redaktur 2nd Pass)")
        print_console_safe("  [R] Retry / Regenerate")
        print_console_safe("  [E] Add Context Note / Glossary & Retry")
        print_console_safe("  [S] Skip / Keep Original Wikitext")
        print_console_safe("  [Q] Quit & Save Draft")


def render_step_indicator(action_name: str, status: str = "done", detail: str = "") -> None:
    """Renders a single-line step execution status."""
    if is_rich_enabled():
        console = get_console()
        if status == "done":
            prefix = "[bold green]✔[/]"
        elif status == "skip":
            prefix = "[bold dim]○[/]"
        elif status == "warn":
            prefix = "[bold yellow]⚠[/]"
        elif status == "error":
            prefix = "[bold red]✖[/]"
        else:
            prefix = "[bold cyan]•[/]"
        detail_str = f" [dim]({detail})[/]" if detail else ""
        console.print(f" {prefix} {action_name}{detail_str}")
    else:
        if status in ("done", "ok"):
            print_console_safe(f"[+] {action_name} {detail}".strip())
        elif status == "warn":
            print_console_safe(f"[!] Warning: {action_name} {detail}".strip())
        elif status == "error":
            print_console_safe(f"[!] {action_name} {detail}".strip())
        else:
            print_console_safe(f"[*] {action_name} {detail}".strip())

def render_diff_view(source_en: str, draft_id: str) -> None:
    """Displays a dual-pane or side-by-side comparison between source EN and draft ID."""
    if is_rich_enabled():
        console = get_console()
        p1 = Panel(
            source_en.strip(),
            title="[bold cyan]Source EN[/]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        p2 = Panel(
            draft_id.strip(),
            title="[bold green]Draft ID[/]",
            border_style="green",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_row(p1, p2)
        console.print()
        console.print(grid)
        console.print()
    else:
        print_console_safe("\n" + "=" * 36 + " [SOURCE EN] " + "=" * 24)
        print_console_safe(source_en.strip())
        print_console_safe("\n" + "=" * 36 + " [DRAFT ID]  " + "=" * 24)
        print_console_safe(draft_id.strip())
        print_console_safe("=" * 72)


class UI:
    """Unified terminal UI controller supporting both Rich styling and clean ASCII fallbacks."""

    @staticmethod
    def is_rich() -> bool:
        return is_rich_enabled()

    @staticmethod
    def console() -> Any:
        return get_console()

    @classmethod
    def info(cls, message: str) -> None:
        if cls.is_rich():
            cls.console().print(f"[bold cyan]•[/] {message}")
        else:
            print_console_safe(f"[*] {message}")

    @classmethod
    def success(cls, message: str) -> None:
        if cls.is_rich():
            cls.console().print(f"[bold green]✔[/] [green]{message}[/]")
        else:
            print_console_safe(f"[+] {message}")

    @classmethod
    def warning(cls, message: str) -> None:
        if cls.is_rich():
            cls.console().print(f"[bold yellow]⚠[/] [yellow]{message}[/]")
        else:
            print_console_safe(f"[!] Warning: {message}")

    @classmethod
    def error(cls, message: str) -> None:
        if cls.is_rich():
            cls.console().print(f"[bold red]✖[/] [red]{message}[/]")
        else:
            print_console_safe(f"[!] {message}")

    @classmethod
    def banner(cls, model: Optional[str] = None, topic: Optional[str] = None) -> None:
        print_banner(model=model, topic=topic)

    @classmethod
    def sections_table(cls, sections: List[Any]) -> None:
        render_sections_table(sections)

    @classmethod
    def section_header(cls, index: int, total: int, title: str, words: int, chars: int) -> None:
        render_section_header(index, total, title, words, chars)

    @classmethod
    def review_menu(cls, section_title: str) -> None:
        render_review_menu(section_title)

    @classmethod
    def diff(cls, source_en: str, draft_id: str) -> None:
        render_diff_view(source_en, draft_id)

    @classmethod
    def step(cls, action: str, status: str = "done", detail: str = "") -> None:
        render_step_indicator(action, status=status, detail=detail)


ui = UI()

def slugify(text: str) -> str:
    """Converts an article title into a clean filename slug."""
    cleaned = re.sub(r"[^\w\s-]", "", text).strip()
    return re.sub(r"[-\s]+", "_", cleaned).lower()


def load_env_file(env_path: Optional[Path] = None) -> None:
    """Searches for and loads environment variables from a .env file.

    Pure-Python implementation without external dependencies.
    Searches in the specified path, or scans current working directory, project
    root, and parent directories for a `.env` file.
    """
    target_file: Optional[Path] = None
    if env_path is not None:
        if env_path.is_file():
            target_file = env_path
    else:
        candidates: List[Path] = []
        for base in [Path.cwd().resolve(), Path(__file__).resolve().parent.parent.resolve()]:
            curr = base
            while curr not in candidates:
                candidates.append(curr)
                if curr.parent == curr:
                    break
                curr = curr.parent
        for dir_path in candidates:
            candidate_file = dir_path / ".env"
            if candidate_file.is_file():
                target_file = candidate_file
                break

    if not target_file:
        return

    try:
        content = target_file.read_text(encoding="utf-8")
    except OSError:
        return

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            if len(val) >= 2:
                val = val[1:-1]
        if key not in os.environ:
            os.environ[key] = val
