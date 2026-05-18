#!/usr/bin/env python3
"""
🦞 rag — Minimal Agent Memory System Launcher

Usage:
    rag                   → Interactive agent picker, then start session
    rag list              → Show registered agents
    rag start [agent]     → Start session (picker if no agent given)
    rag end [agent]       → End session with summary
    rag status [agent]    → Show pending tasks & active session
    rag context [agent]   → Generate & display runtime prompt
    rag search <query>    → FTS5 knowledge search
    rag daily             → Index daily memory files
    rag add-note          → Interactive note creation

Examples:
    rag start             → pick from list
    rag start linux-admin → start directly
    rag search "browser automation"
"""

import sys
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich import box

# Ensure scripts dir is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

from db import (
    register_agent, get_agent, list_agents,
    start_session, end_session, build_runtime_prompt, build_context,
    save_checkpoint, get_pending_tasks, search_notes, search_sessions,
    add_note, now,
)

# ── Globals ──────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="rag",
    help="🦞 Minimal Agent Memory System — manage agents & memory",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()
BASE = Path.home() / "simple-rag-arch"
MEMORY_DIR = Path.home() / "linux-admin-workspace" / "memory"

# Known agents for auto-registration
AGENT_MAP: dict[str, tuple[str, str, str]] = {
    "main": ("main", "Ricchys", "agents/ricchys_agent.md"),
    "linux-admin": ("linux-admin", "Edgy", "agents/edgy_agent.md"),
    "ops": ("ops", "Ops Agent", "agents/ops_agent.md"),
    "coder": ("coder", "Coder Agent", "agents/coder_agent.md"),
    "research": ("research", "Research Agent", "agents/research_agent.md"),
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ensure_agent(agent_id: str | None) -> str:
    """Resolve agent: use given ID, or let user pick interactively."""
    if agent_id:
        # Try to auto-register if not found
        if not get_agent(agent_id):
            if agent_id in AGENT_MAP:
                aid, name, pfile = AGENT_MAP[agent_id]
                register_agent(aid, name, pfile)
                console.print(f"[green]✓[/] Auto-registered agent [bold]{name}[/] ({aid})")
            else:
                console.print(f"[red]✗[/] Unknown agent: [bold]{agent_id}[/]")
                raise typer.Exit(code=1)
        return agent_id

    # Interactive picker
    agents = list_agents()
    if not agents:
        console.print("[yellow]⚠ No agents registered. Creating defaults...[/]")
        for aid, name, pfile in AGENT_MAP.values():
            register_agent(aid, name, pfile)
        agents = list_agents()

    console.print("\n[bold]🦞 Select an agent:[/]")
    for i, a in enumerate(agents, 1):
        console.print(f"  [cyan]{i}.[/] {a['name']} [dim]({a['id']})[/]")
    console.print(f"  [cyan]q.[/] Quit")

    choice = Prompt.ask("Choice", default="1")
    if choice.lower() in ("q", "quit", "exit"):
        raise typer.Exit()

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(agents):
            return agents[idx]["id"]
    except ValueError:
        pass

    console.print("[red]Invalid choice[/]")
    raise typer.Exit(code=1)


def _get_active_session(agent_id: str) -> int | None:
    """Get the active session id for an agent, or None."""
    sid_path = BASE / "runtime" / f".active_session_{agent_id}"
    if sid_path.exists():
        return int(sid_path.read_text().strip())
    return None


def _render_context(agent_id: str) -> str:
    """Generate and save runtime prompt, return it as string."""
    prompt = build_runtime_prompt(agent_id)
    rt_path = BASE / "runtime" / "runtime_prompt.md"
    rt_path.parent.mkdir(parents=True, exist_ok=True)
    rt_path.write_text(prompt)
    return prompt


# ── Commands ─────────────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def default(ctx: typer.Context):
    """Run `rag start` when no subcommand given."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(start, agent=None)


@app.command()
def list(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show full details")] = False,
):
    """List all registered agents."""
    agents = list_agents()
    if not agents:
        console.print("[yellow]⚠ No agents registered.[/]")
        return

    table = Table(title="🦞 Registered Agents", box=box.ROUNDED)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Persona")
    table.add_column("Status")
    table.add_column("Created")

    for a in agents:
        table.add_row(
            a["id"],
            a["name"],
            a["persona_file"].replace("agents/", ""),
            a["status"],
            a["created_at"][:19],
        )

    console.print(table)

    if verbose:
        for a in agents:
            tasks = get_pending_tasks(a["id"])
            sid = _get_active_session(a["id"])
            if tasks or sid:
                console.print(f"\n[bold]{a['name']}[/]:")
                if sid:
                    console.print(f"  Active session: [cyan]{sid}[/]")
                for t in tasks:
                    console.print(f"  Task [bold]{t['task_id']}[/] step {t['step']} → {t['status']}")


@app.command()
def start(
    agent: Annotated[Optional[str], typer.Argument(help="Agent ID (interactive if omitted)")] = None,
    max_tokens: Annotated[int, typer.Option("--max-tokens", "-t", help="Context budget")] = 6000,
):
    """Start a new session and generate runtime prompt."""
    agent_id = _ensure_agent(agent)

    # Check for existing active session
    existing = _get_active_session(agent_id)
    if existing is not None:
        console.print(f"[yellow]⚠ Active session [bold]{existing}[/] already exists for [bold]{agent_id}[/][/]")
        if not Confirm.ask("Start new session anyway?"):
            console.print("[dim]Using existing session. Generate context...[/]")
            prompt = _render_context(agent_id)
            console.print(Panel(Markdown(prompt), title="📋 Runtime Context", border_style="green"))
            return

    # Start session
    sid = start_session(agent_id)
    sid_path = BASE / "runtime" / f".active_session_{agent_id}"
    sid_path.parent.mkdir(parents=True, exist_ok=True)
    sid_path.write_text(str(sid))

    # Generate prompt
    prompt = _render_context(agent_id)

    agent_info = get_agent(agent_id)
    name = agent_info["name"] if agent_info else agent_id

    console.print(Panel(
        f"[bold green]Session {sid} started[/] for [bold]{name}[/] [dim]({agent_id})[/]\n"
        f"[bold]Runtime prompt:[/] [cyan]{BASE / 'runtime' / 'runtime_prompt.md'}[/]\n"
        f"[bold]Context budget:[/] ~{prompt.count(' ')} words / {max_tokens} tokens",
        title="🚀 Agent Launched",
        border_style="bright_green",
    ))

    # Prompt for immediate action
    console.print("\n[dim]Ready. Use [bold]rag end {agent_id}[/] to close session when done.[/]")
    if get_pending_tasks(agent_id):
        console.print(f"[yellow]⚠ {len(get_pending_tasks(agent_id))} pending task(s) — check [bold]rag status {agent_id}[/][/]")


@app.command()
def end(
    agent: Annotated[Optional[str], typer.Argument(help="Agent ID (interactive if omitted)")] = None,
    summary: Annotated[Optional[str], typer.Option("--summary", "-s", help="Session summary")] = None,
    auto: Annotated[bool, typer.Option("--auto", "-a", help="Auto-summarize from daily memory")] = False,
    worked: Annotated[Optional[str], typer.Option("--worked", "-w", help="Comma-separated what worked")] = None,
    failed: Annotated[Optional[str], typer.Option("--failed", "-f", help="Comma-separated what failed")] = None,
):
    """End an active session with summary."""
    agent_id = _ensure_agent(agent)

    sid = _get_active_session(agent_id)
    if sid is None:
        console.print(f"[red]✗ No active session found for [bold]{agent_id}[/][/]")
        console.print("  Start one with: [bold]rag start {agent_id}[/]")
        raise typer.Exit(code=1)

    # Gather summary
    if not summary and not auto:
        summary = Prompt.ask("[bold]Session summary[/]", default="(completed)")
    elif auto:
        today = datetime.now().strftime("%Y-%m-%d")
        mem_file = MEMORY_DIR / f"{today}.md"
        if mem_file.exists():
            content = mem_file.read_text()
            summary = content[:500]
            # Auto-extract work status
            lines = content.split("\n")
            worked_list = [l.strip("- ").strip() for l in lines
                          if "✅" in l or "done" in l.lower() or "completed" in l.lower()]
            failed_list = [l.strip("- ").strip() for l in lines
                          if "❌" in l or "blocked" in l.lower() or "failed" in l.lower()]
            worked = ",".join(worked_list) if worked_list else worked
            failed = ",".join(failed_list) if failed_list else failed
            console.print(f"[dim]📖 Auto-summarized from {today}.md ({len(content)} chars)[/]")
        else:
            summary = summary or "(completed)"

    w_list = [x.strip() for x in worked.split(",")] if worked else []
    f_list = [x.strip() for x in failed.split(",")] if failed else []

    result = end_session(sid, summary=summary, what_worked=w_list, what_failed=f_list)

    # Clean up marker
    sid_path = BASE / "runtime" / f".active_session_{agent_id}"
    if sid_path.exists():
        sid_path.unlink()

    # Show results
    table = Table(title=f"✅ Session {result['id']} Ended", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value")
    table.add_row("Agent", agent_id)
    table.add_row("Duration", f"{result.get('duration_s', '?')}s")
    table.add_row("Tokens", str(result.get("token_count", 0)))
    table.add_row("Summary", (result.get("summary") or "")[:80])
    console.print(table)

    if auto or worked or failed:
        for w in w_list[:3]:
            if w.lower() in ('', 'none', 'n/a', '-'):
                continue
            add_note(agent_id, f"✅ {w[:60]}", w, ["session-auto"], 1)
        for f_item in f_list[:3]:
            if f_item.lower() in ('', 'none', 'n/a', '-'):
                continue
            add_note(agent_id, f"⚠️ {f_item[:60]}", f_item, ["session-auto", "blocker"], 3)


@app.command()
def status(
    agent: Annotated[Optional[str], typer.Argument(help="Agent ID, or all if omitted")] = None,
):
    """Show agent status — active session, pending tasks, recent memory."""
    if agent:
        agents_to_show = [agent]
    else:
        agents_to_show = [a["id"] for a in list_agents()]
        if not agents_to_show:
            console.print("[yellow]⚠ No agents registered.[/]")
            return

    for aid in agents_to_show:
        try:
            _ensure_agent(aid)
        except typer.Exit:
            continue

        agent_info = get_agent(aid)
        if not agent_info:
            continue

        console.print(f"\n[bold]{agent_info['name']}[/] [dim]({aid})[/]")

        # Active session
        sid = _get_active_session(aid)
        if sid:
            console.print(f"  [green]●[/] Active session: [bold]{sid}[/]")
        else:
            console.print(f"  [dim]○ No active session[/]")

        # Pending tasks
        tasks = get_pending_tasks(aid)
        if tasks:
            task_table = Table(box=box.SIMPLE, show_header=True)
            task_table.add_column("Task", style="yellow")
            task_table.add_column("Step")
            task_table.add_column("Status")
            task_table.add_column("Retries")
            for t in tasks:
                status_style = {"running": "green", "pending": "yellow", "failed": "red"}.get(t["status"], "white")
                task_table.add_row(
                    t["task_id"],
                    str(t["step"]),
                    f"[{status_style}]{t['status']}[/]",
                    str(t["retry_count"]),
                )
            console.print(task_table)
        else:
            console.print("  [dim]✅ No pending tasks[/]")

        # Search recent notes from this agent
        recent = search_notes(f"agent:{aid}", limit=3)
        if recent:
            console.print("  [dim]Recent notes:[/]")
            for n in recent:
                console.print(f"    📝 {n['title']}")


@app.command()
def context(
    agent: Annotated[Optional[str], typer.Argument(help="Agent ID (interactive if omitted)")] = None,
    show: Annotated[bool, typer.Option("--show", "-s", help="Print prompt to stdout")] = True,
):
    """Generate and display runtime context prompt."""
    agent_id = _ensure_agent(agent)
    prompt = _render_context(agent_id)

    console.print(Panel(
        f"[bold]Context generated for {agent_id}[/]\n"
        f"Written to: [cyan]{BASE / 'runtime' / 'runtime_prompt.md'}[/]",
        border_style="green",
    ))

    if show:
        console.print(Panel(Markdown(prompt), title="📋 Runtime Context", border_style="dim"))


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query (FTS5)")],
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max results")] = 5,
):
    """Search memory — notes, sessions, tags."""
    console.print(f"[bold]🔍 Searching:[/] [cyan]{query}[/]\n")

    # Notes
    notes = search_notes(query, limit=limit)
    if notes:
        table = Table(title="📝 Notes", box=box.ROUNDED)
        table.add_column("Title", style="bold")
        table.add_column("Tags")
        table.add_column("Snippet")
        for n in notes:
            tags = n.get("tags", "") or ""
            snippet = n["content"][:80] + "..." if len(n["content"]) > 80 else n["content"]
            table.add_row(n["title"], f"[dim]{tags}[/]", snippet)
        console.print(table)
    else:
        console.print("[dim]No notes found[/]")

    # Sessions
    sessions = search_sessions(query, limit=limit)
    if sessions:
        table2 = Table(title="💬 Sessions", box=box.ROUNDED)
        table2.add_column("ID")
        table2.add_column("Agent")
        table2.add_column("Summary")
        for s in sessions:
            summary = (s.get("summary") or "")[:80]
            table2.add_row(str(s["id"]), s.get("agent_id", "?"), summary)
        console.print(table2)

    if not notes and not sessions:
        console.print(f"[yellow]No results for '{query}'[/]")


@app.command()
def daily(
    agent: Annotated[Optional[str], typer.Argument(help="Agent to assign notes to")] = "main",
):
    """Index new daily memory files into RAG notes."""
    if not MEMORY_DIR.exists():
        console.print(f"[red]✗ Memory directory not found: {MEMORY_DIR}[/]")
        return

    files = sorted(MEMORY_DIR.glob("*.md"))
    indexed = 0
    for fpath in files:
        key = f"_{fpath.stem}"
        marker = BASE / "runtime" / f".indexed{key}"
        if marker.exists():
            continue

        content = fpath.read_text()
        title = f"Daily Memory: {fpath.stem}"
        add_note(agent, title, content[:1000], ["daily-memory"], 1)
        marker.write_text("1")
        indexed += 1
        console.print(f"  [green]✓[/] Indexed: [bold]{fpath.name}[/] ({len(content)} chars)")

    if indexed == 0:
        console.print("[dim]✅ All daily memory files already indexed[/]")
    else:
        console.print(f"[bold green]✅ Indexed {indexed} new file(s)[/]")


@app.command()
def add_note_cmd(
    title: Annotated[str, typer.Option("--title", "-t", prompt="Note title")],
    content: Annotated[str, typer.Option("--content", "-c", prompt="Note content")],
    agent: Annotated[Optional[str], typer.Option("--agent", "-a", help="Agent ID")] = "main",
    tags: Annotated[Optional[str], typer.Option("--tags", help="Comma-separated tags")] = None,
    importance: Annotated[int, typer.Option("--importance", "-i", help="0-5")] = 1,
):
    """Add a new knowledge note interactively."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    note = add_note(agent, title, content, tag_list, importance)
    console.print(f"[green]✓[/] Note #{note['id']} saved: [bold]{title}[/]")


@app.command()
def checkpoint(
    task: Annotated[str, typer.Option("--task", "-t", prompt="Task ID")],
    step: Annotated[int, typer.Option("--step", "-s", prompt="Step number")],
    agent: Annotated[Optional[str], typer.Option("--agent", "-a", help="Agent ID (interactive)")] = None,
    status: Annotated[str, typer.Option("--status", help="pending|running|success|failed")] = "running",
):
    """Save a workflow checkpoint."""
    agent_id = _ensure_agent(agent)
    sid = _get_active_session(agent_id)

    cp = save_checkpoint(sid, task, step, status)
    status_icon = {"running": "▶️", "pending": "⏳", "success": "✅", "failed": "❌"}.get(status, "📌")
    console.print(f"[green]✓[/] {status_icon} Checkpoint #{cp['id']}: [bold]{task}[/] step {step} → {status}")


# ── Entry ────────────────────────────────────────────────────────────────────

def main():
    """Entry point that handles the venv path."""
    app()


if __name__ == "__main__":
    app()
