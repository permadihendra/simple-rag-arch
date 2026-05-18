#!/usr/bin/env python3
"""
🦞 rag — Minimal Agent Memory System Launcher

Usage:
    rag                          → Pick platform → pick agent → start session
    rag start [platform] [agent] → Start with context
    rag list                     → Show registered agents
    rag end [agent]              → End session with summary
    rag status [agent]           → Show pending tasks & active session
    rag context [agent]          → Generate & display runtime prompt
    rag search <query>           → FTS5 knowledge search
    rag daily                    → Index daily memory files
    rag add-note                 → Interactive note creation

Examples:
    rag start                         → pick platform → pick agent
    rag start openclaw                → pick agent → start
    rag start openclaw linux-admin    → direct start
    rag search "browser automation"
"""

import sys
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich import box

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

from db import (
    register_agent, get_agent, list_agents, _conn,
    start_session, end_session, build_runtime_prompt, build_context,
    save_checkpoint, get_pending_tasks, search_notes, search_sessions,
    add_note, now,
)

# ── Globals ──────────────────────────────────────────────────────────────────

app = typer.Typer(name="rag", help="🦞 Minimal Agent Memory System",
                  add_completion=False, rich_markup_mode="rich")
console = Console()
BASE = Path.home() / "simple-rag-arch"
MEMORY_DIR = Path.home() / "linux-admin-workspace" / "memory"

PLATFORMS: dict[str, dict] = {
    "openclaw": {"name": "OpenClaw",  "icon": "🤖", "desc": "OpenClaw AI agent platform"},
    "pi-code":  {"name": "Pi Code",   "icon": "⚡",  "desc": "Pi.dev code agent"},
}

AGENT_MAP: dict[str, tuple[str, str, str]] = {
    "main":        ("main",        "Ricchys",        "agents/ricchys_agent.md"),
    "linux-admin": ("linux-admin", "Edgy",           "agents/edgy_agent.md"),
    "pi-code":     ("pi-code",     "Pi Code Agent",  "agents/pi_code_agent.md"),
    "ops":         ("ops",         "Ops Agent",      "agents/ops_agent.md"),
    "coder":       ("coder",       "Coder Agent",    "agents/coder_agent.md"),
    "research":    ("research",    "Research Agent", "agents/research_agent.md"),
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _agents_by_platform(platform: str | None = None) -> list[dict]:
    c = _conn()
    if platform:
        rows = c.execute(
            "SELECT * FROM agents WHERE status='active' AND platform=? ORDER BY id",
            (platform,),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM agents WHERE status='active' ORDER BY platform, id"
        ).fetchall()
    c.close()
    return [dict(r) for r in rows]

def _pick_platform() -> str:
    console.print("\n[bold]🦞 Select a platform:[/]")
    pids = list(PLATFORMS.keys())
    for i, pid in enumerate(pids, 1):
        p = PLATFORMS[pid]
        console.print(f"  [cyan]{i}.[/] {p['icon']} {p['name']} [dim]— {p['desc']}[/]")
    console.print(f"  [cyan]q.[/] Quit")
    choice = Prompt.ask("Choice", default="1")
    if choice.lower() in ("q", "quit", "exit"):
        raise typer.Exit()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(pids):
            return pids[idx]
    except ValueError:
        pass
    console.print("[red]Invalid choice[/]")
    raise typer.Exit(code=1)

def _pick_agent(agents: list[dict], platform: str | None = None) -> str:
    tag = f" on [bold]{PLATFORMS.get(platform,{}).get('name',platform)}[/]" if platform else ""
    console.print(f"\n[bold]🦞 Select an agent{tag}:[/]")
    for i, a in enumerate(agents, 1):
        icon = PLATFORMS.get(a.get("platform", ""), {}).get("icon", "")
        console.print(f"  [cyan]{i}.[/] {icon} {a['name']} [dim]({a['id']})[/]")
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

def _resolve_platform(p: str | None) -> str:
    if p:
        if p not in PLATFORMS:
            console.print(f"[red]✗ Unknown platform: [bold]{p}[/]. Options: {', '.join(PLATFORMS)}[/]")
            raise typer.Exit(code=1)
        return p
    return _pick_platform()

def _resolve_agent(aid: str | None, platform: str | None = None) -> str:
    if aid:
        if not get_agent(aid):
            if aid in AGENT_MAP:
                id_, name, pfile = AGENT_MAP[aid]
                plat = platform or "openclaw"
                register_agent(id_, name, pfile)
                c = _conn()
                c.execute("UPDATE agents SET platform=? WHERE id=?", (plat, id_))
                c.commit(); c.close()
                console.print(f"[green]✓[/] Auto-registered [bold]{name}[/] ({id_}) on [bold]{plat}[/]")
            else:
                console.print(f"[red]✗ Unknown agent: {aid}[/]")
                raise typer.Exit(code=1)
        return aid
    agents = _agents_by_platform(platform)
    if not agents:
        console.print(f"[yellow]⚠ No agents for platform '{platform or 'any'}'. Use [bold]rag add-note[/] to store knowledge.[/]")
        raise typer.Exit(code=1)
    return _pick_agent(agents, platform)

def _active_session(agent_id: str) -> int | None:
    p = BASE / "runtime" / f".active_session_{agent_id}"
    return int(p.read_text().strip()) if p.exists() else None

def _generate_context(agent_id: str) -> str:
    prompt = build_runtime_prompt(agent_id)
    p = BASE / "runtime" / "runtime_prompt.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(prompt)
    return prompt

def _render_panel(title: str, content: str, style: str = "green") -> Panel:
    return Panel(content, title=f"📋 {title}", border_style=style)

# ── Commands ─────────────────────────────────────────────────────────────────

def _show_menu():
    """Interactive menu when rag is called without arguments."""
    console.print("\n[bold]🦞 agent memory system[/]")
    console.print("  [cyan]1.[/] 🚀 Start session")
    console.print("  [cyan]2.[/] 📋 List agents")
    console.print("  [cyan]3.[/] 🔍 Search memory")
    console.print("  [cyan]4.[/] 📖 Index daily memory")
    console.print("  [cyan]5.[/] 📝 Add note")
    console.print("  [cyan]q.[/]  Quit")
    choice = Prompt.ask("Choice", default="1")
    if choice == "1":
        start()
    elif choice == "2":
        list_cmd()
    elif choice == "3":
        q = Prompt.ask("Search query")
        search(q)
    elif choice == "4":
        daily()
    elif choice == "5":
        add_note_cmd()

@app.callback()
def main_callback():
    """🦞 Minimal Agent Memory System"""
    pass

@app.command(name="list")
def list_cmd(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show full details")] = False,
):
    """List all agents grouped by platform."""
    agents = list_agents()
    if not agents:
        console.print("[yellow]⚠ No agents registered.[/]")
        return

    # Group by platform
    by_plat: dict[str, list[dict]] = {}
    for a in agents:
        by_plat.setdefault(a.get("platform", "other"), []).append(a)

    for plat, ags in sorted(by_plat.items()):
        pinfo = PLATFORMS.get(plat, {})
        icon = pinfo.get("icon", "")
        pname = pinfo.get("name", plat)
        table = Table(title=f"{icon} {pname}", box=box.ROUNDED)
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Persona")
        table.add_column("Status")
        table.add_column("Created")
        for a in ags:
            table.add_row(a["id"], a["name"],
                          a["persona_file"].replace("agents/", ""),
                          a["status"], a["created_at"][:19])
        console.print(table)

    if verbose:
        for a in agents:
            tasks = get_pending_tasks(a["id"])
            sid = _active_session(a["id"])
            if tasks or sid:
                console.print(f"\n[bold]{a['name']}[/]:")
                if sid:
                    console.print(f"  Active session: [cyan]{sid}[/]")
                for t in tasks:
                    console.print(f"  Task [bold]{t['task_id']}[/] step {t['step']} → {t['status']}")

@app.command()
def start(
    platform: Annotated[Optional[str], typer.Argument(help="Platform (openclaw, pi-code)")] = None,
    agent: Annotated[Optional[str], typer.Argument(help="Agent ID")] = None,
    max_tokens: Annotated[int, typer.Option("--max-tokens", "-t", help="Context budget")] = 6000,
):
    """Start a new session — two-level platform → agent flow."""
    plat = _resolve_platform(platform)
    aid = _resolve_agent(agent, plat)

    existing = _active_session(aid)
    if existing is not None:
        console.print(f"[yellow]⚠ Active session [bold]{existing}[/] already exists for [bold]{aid}[/][/]")
        if not Confirm.ask("Start new session anyway?"):
            console.print("[dim]Refreshing context...[/]")
            prompt = _generate_context(aid)
            console.print(_render_panel("Runtime Context (refreshed)", Markdown(prompt), "green"))
            return

    sid = start_session(aid)
    (BASE / "runtime" / f".active_session_{aid}").write_text(str(sid))

    prompt = _generate_context(aid)
    agent_info = get_agent(aid)
    name = agent_info["name"] if agent_info else aid
    plat_info = PLATFORMS.get(plat, {})
    icon = plat_info.get("icon", "")
    plat_label = plat_info.get("name", plat)

    console.print(Panel(
        f"[bold green]Session {sid} started[/]\n"
        f"{icon} [bold]{name}[/] [dim]({aid})[/] on [bold]{plat_label}[/]\n"
        f"[dim]Runtime prompt:[/] [cyan]{BASE / 'runtime' / 'runtime_prompt.md'}[/]\n"
        f"[dim]Context budget:[/] ~{len(prompt.split())} words / {max_tokens} tokens",
        title="🚀 Agent Launched", border_style="bright_green",
    ))

    console.print(f"\n[dim]Use [bold]rag end {aid}[/] to close session when done.[/]")
    pending = get_pending_tasks(aid)
    if pending:
        console.print(f"[yellow]⚠ {len(pending)} pending task(s) — check [bold]rag status {aid}[/][/]")

    # ── Show launch command ──
    rt_path = BASE / 'runtime' / 'runtime_prompt.md'

    if plat == 'openclaw':
        console.print(f"\n[bold]→ Next:[/] Run [bold]openclaw[/] in this terminal")
        console.print(f"  [dim]Context: {rt_path}[/]")
    elif plat == 'pi-code':
        cmd = f'pi --append-system-prompt {rt_path}'
        console.print(f"\n[bold]→ Next:[/] Run [bold]{cmd}[/] in this terminal")
    else:
        console.print(f"  [dim]Context ready at: {rt_path}. Launch the platform manually.[/]")

@app.command()
def end(
    agent: Annotated[Optional[str], typer.Argument(help="Agent ID (interactive if omitted)")] = None,
    summary: Annotated[Optional[str], typer.Option("--summary", "-s", help="Session summary")] = None,
    auto: Annotated[bool, typer.Option("--auto", "-a", help="Auto-summarize from daily memory")] = False,
    worked: Annotated[Optional[str], typer.Option("--worked", "-w", help="Comma-separated what worked")] = None,
    failed: Annotated[Optional[str], typer.Option("--failed", "-f", help="Comma-separated what failed")] = None,
):
    """End an active session with summary."""
    aid = _resolve_agent(agent)
    sid = _active_session(aid)
    if sid is None:
        console.print(f"[red]✗ No active session for [bold]{aid}[/]. Start one: [bold]rag start {aid}[/][/]")
        raise typer.Exit(code=1)

    if not summary and not auto:
        summary = Prompt.ask("[bold]Session summary[/]", default="(completed)")
    elif auto:
        today = datetime.now().strftime("%Y-%m-%d")
        mf = MEMORY_DIR / f"{today}.md"
        if mf.exists():
            content = mf.read_text()
            summary = content[:500]
            lines = content.split("\n")
            wl = [l.strip("- ").strip() for l in lines if "✅" in l or "done" in l.lower() or "completed" in l.lower()]
            fl = [l.strip("- ").strip() for l in lines if "❌" in l or "blocked" in l.lower() or "failed" in l.lower()]
            worked = ",".join(wl) if wl else worked
            failed = ",".join(fl) if fl else failed
            console.print(f"[dim]📖 Auto-summarized from {today}.md ({len(content)} chars)[/]")
        else:
            summary = summary or "(completed)"

    wl = [x.strip() for x in worked.split(",")] if worked else []
    fl = [x.strip() for x in failed.split(",")] if failed else []

    result = end_session(sid, summary=summary, what_worked=wl, what_failed=fl)

    sp = BASE / "runtime" / f".active_session_{aid}"
    if sp.exists(): sp.unlink()

    tbl = Table(title=f"✅ Session {result['id']} Ended", box=box.ROUNDED)
    tbl.add_column("Metric", style="cyan"); tbl.add_column("Value")
    tbl.add_row("Agent", aid); tbl.add_row("Duration", f"{result.get('duration_s','?')}s")
    tbl.add_row("Tokens", str(result.get("token_count", 0)))
    tbl.add_row("Summary", (result.get("summary") or "")[:80])
    console.print(tbl)

    if auto or worked or failed:
        for w in wl[:3]:
            if w.lower() in ('', 'none', 'n/a', '-'): continue
            add_note(aid, f"✅ {w[:60]}", w, ["session-auto"], 1)
        for f_ in fl[:3]:
            if f_.lower() in ('', 'none', 'n/a', '-'): continue
            add_note(aid, f"⚠️ {f_[:60]}", f_, ["session-auto", "blocker"], 3)

@app.command()
def status(
    agent: Annotated[Optional[str], typer.Argument(help="Agent ID, or all if omitted")] = None,
):
    """Show agent status — active session, pending tasks."""
    if agent:
        aids = [agent]
    else:
        aids = [a["id"] for a in list_agents()]
        if not aids:
            console.print("[yellow]⚠ No agents registered.[/]"); return

    for aid in aids:
        try:
            _resolve_agent(aid)
        except typer.Exit:
            continue
        info = get_agent(aid)
        if not info: continue
        plat = info.get("platform", "?")
        picon = PLATFORMS.get(plat, {}).get("icon", "")
        console.print(f"\n{picon} [bold]{info['name']}[/] [dim]({aid})[/]")

        sid = _active_session(aid)
        console.print(f"  [{'green' if sid else 'dim'}]{'●' if sid else '○'}[/] {f'Active session: [bold]{sid}[/]' if sid else 'No active session'}")

        tasks = get_pending_tasks(aid)
        if tasks:
            t = Table(box=box.SIMPLE)
            t.add_column("Task", style="yellow"); t.add_column("Step")
            t.add_column("Status"); t.add_column("Retries")
            for tk in tasks:
                st = {"running": "green", "pending": "yellow", "failed": "red"}.get(tk["status"], "white")
                t.add_row(tk["task_id"], str(tk["step"]), f"[{st}]{tk['status']}[/]", str(tk["retry_count"]))
            console.print(t)
        else:
            console.print("  [dim]✅ No pending tasks[/]")

@app.command()
def context(
    agent: Annotated[Optional[str], typer.Argument(help="Agent ID (interactive)")] = None,
    show: Annotated[bool, typer.Option("--show", "-s", help="Print prompt")] = True,
):
    """Generate runtime context prompt."""
    aid = _resolve_agent(agent)
    prompt = _generate_context(aid)
    console.print(Panel(f"[bold]Context generated for {aid}[/]\n→ {BASE / 'runtime' / 'runtime_prompt.md'}", border_style="green"))
    if show:
        console.print(_render_panel("Runtime Context", Markdown(prompt), "dim"))

@app.command()
def search(
    query: Annotated[str, typer.Argument(help="FTS5 search query")],
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max results")] = 5,
):
    """Search memory notes and sessions."""
    console.print(f"[bold]🔍 Searching:[/] [cyan]{query}[/]\n")
    notes = search_notes(query, limit)
    if notes:
        t = Table(title="📝 Notes", box=box.ROUNDED)
        t.add_column("Title", style="bold"); t.add_column("Tags")
        t.add_column("Snippet")
        for n in notes:
            tags = n.get("tags", "") or ""
            snip = n["content"][:80] + "..." if len(n["content"]) > 80 else n["content"]
            t.add_row(n["title"], f"[dim]{tags}[/]", snip)
        console.print(t)
    sessions = search_sessions(query, limit)
    if sessions:
        t2 = Table(title="💬 Sessions", box=box.ROUNDED)
        t2.add_column("ID"); t2.add_column("Agent"); t2.add_column("Summary")
        for s in sessions:
            t2.add_row(str(s["id"]), s.get("agent_id", "?"), (s.get("summary") or "")[:80])
        console.print(t2)
    if not notes and not sessions:
        console.print(f"[yellow]No results for '{query}'[/]")

@app.command()
def daily(
    agent: Annotated[Optional[str], typer.Argument(help="Agent for notes")] = "main",
):
    """Index new daily memory files into RAG notes."""
    if not MEMORY_DIR.exists():
        console.print(f"[red]✗ Memory directory not found: {MEMORY_DIR}[/]"); return
    indexed = 0
    for fpath in sorted(MEMORY_DIR.glob("*.md")):
        marker = BASE / "runtime" / f".indexed_{fpath.stem}"
        if marker.exists(): continue
        content = fpath.read_text()
        add_note(agent, f"Daily: {fpath.stem}", content[:1000], ["daily-memory"], 1)
        marker.write_text("1"); indexed += 1
        console.print(f"  [green]✓[/] Indexed: [bold]{fpath.name}[/]")
    console.print("[dim]✅ All up to date[/]" if indexed == 0 else f"[bold green]✅ Indexed {indexed} file(s)[/]")

@app.command()
def add_note_cmd(
    title: Annotated[str, typer.Option("--title", "-t", prompt="Note title")],
    content: Annotated[str, typer.Option("--content", "-c", prompt="Note content")],
    agent: Annotated[Optional[str], typer.Option("--agent", "-a")] = "main",
    tags: Annotated[Optional[str], typer.Option("--tags")] = None,
    importance: Annotated[int, typer.Option("--importance", "-i")] = 1,
):
    """Add a knowledge note interactively."""
    note = add_note(agent, title, content, [t.strip() for t in tags.split(",")] if tags else [], importance)
    console.print(f"[green]✓[/] Note #{note['id']}: [bold]{title}[/]")

@app.command()
def checkpoint(
    task: Annotated[str, typer.Option("--task", "-t", prompt="Task ID")],
    step: Annotated[int, typer.Option("--step", "-s", prompt="Step number")],
    agent: Annotated[Optional[str], typer.Option("--agent", "-a")] = None,
    status: Annotated[str, typer.Option("--status")] = "running",
):
    """Save a workflow checkpoint."""
    aid = _resolve_agent(agent)
    sid = _active_session(aid)
    cp = save_checkpoint(sid, task, step, status)
    icons = {"running": "▶️", "pending": "⏳", "success": "✅", "failed": "❌"}
    console.print(f"[green]✓[/] {icons.get(status,'📌')} #{cp['id']}: [bold]{task}[/] step {step} → {status}")

# ── Entry ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        _show_menu()
    else:
        app()
