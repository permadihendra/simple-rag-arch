#!/usr/bin/env python3
"""
openclaw_integrate.py — Unified OpenClaw integration for the RAG memory system.

Usage:
    # Start a new session (generate runtime prompt)
    python openclaw_integrate.py start <agent_id>

    # End current session with auto-summary
    python openclaw_integrate.py end <agent_id> --summary "Did X" --worked "A,B" --failed "C"

    # Quick session end (reads daily memory for auto-summary)
    python openclaw_integrate.py end <agent_id> --auto

    # Check pending tasks
    python openclaw_integrate.py status <agent_id>

    # Save a checkpoint mid-workflow
    python openclaw_integrate.py checkpoint <agent_id> <task_id> <step>

    # Search knowledge
    python openclaw_integrate.py search <query>

    # Inject runtime prompt into OpenClaw (output ready)
    python openclaw_integrate.py context <agent_id>
"""

import sys
import os
import json
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import (
    start_session, end_session, build_runtime_prompt, build_context,
    save_checkpoint, get_pending_tasks, search_notes, search_sessions,
    register_agent, get_agent, list_agents, add_note, now,
)

BASE = os.path.expanduser("~/simple-rag-arch")
MEMORY_DIR = os.path.expanduser("~/linux-admin-workspace/memory")

# ── Known agent mapping ──────────────────────────────────────────────────────

AGENT_MAP = {
    "main": ("main", "Ricchys", "agents/ricchys_agent.md"),
    "linux-admin": ("linux-admin", "Edgy", "agents/edgy_agent.md"),
    "ops": ("ops", "Ops Agent", "agents/ops_agent.md"),
    "coder": ("coder", "Coder Agent", "agents/coder_agent.md"),
    "research": ("research", "Research Agent", "agents/research_agent.md"),
}


def _ensure_registered(agent_id: str) -> None:
    """Auto-register if not in DB."""
    if not get_agent(agent_id):
        if agent_id in AGENT_MAP:
            aid, name, pfile = AGENT_MAP[agent_id]
            register_agent(aid, name, pfile)
            print(f"  ℹ️  Auto-registered agent '{aid}' ({name})")
        else:
            print(f"  ⚠️  Unknown agent '{agent_id}'. Register manually.")
            sys.exit(1)


def cmd_start(agent_id: str, max_tokens: int = 6000):
    """Start a new session and generate runtime prompt."""
    _ensure_registered(agent_id)
    sid = start_session(agent_id)

    prompt = build_runtime_prompt(agent_id, max_tokens=max_tokens)
    rt_path = os.path.join(BASE, "runtime", "runtime_prompt.md")
    os.makedirs(os.path.dirname(rt_path), exist_ok=True)
    with open(rt_path, "w") as f:
        f.write(prompt)

    # Save active session marker
    sid_path = os.path.join(BASE, "runtime", f".active_session_{agent_id}")
    with open(sid_path, "w") as f:
        f.write(str(sid))

    print(f"✅ Session {sid} started for [{agent_id}]")
    print(f"   Runtime prompt → {rt_path}")
    print(f"   Token budget: ~{prompt.count(' ')} words")
    return sid


def cmd_end(agent_id: str, summary: str = "", worked: list = None,
            failed: list = None, auto: bool = False):
    """End session with summary. If --auto, read daily memory for content."""
    _ensure_registered(agent_id)

    sid_path = os.path.join(BASE, "runtime", f".active_session_{agent_id}")
    if os.path.exists(sid_path):
        with open(sid_path) as f:
            session_id = int(f.read().strip())
    else:
        print(f"  ⚠️  No active session found for '{agent_id}'")
        print(f"  💡 Run 'python openclaw_integrate.py start {agent_id}' first")
        sys.exit(1)

    if auto:
        # Auto-summary from daily memory file
        today = datetime.now().strftime("%Y-%m-%d")
        memory_file = os.path.join(MEMORY_DIR, f"{today}.md")
        if os.path.exists(memory_file):
            with open(memory_file) as f:
                content = f.read()
            summary = content[:500] if content else "(session completed)"
            # Also extract sections
            lines = content.split("\n")
            worked = [l.strip("- ").strip() for l in lines if "✅" in l or "done" in l.lower() or "completed" in l.lower()]
            failed = [l.strip("- ").strip() for l in lines if "❌" in l or "blocked" in l.lower() or "failed" in l.lower()]
            print(f"  📖 Auto-summarized from {today}.md ({len(content)} chars)")
        else:
            summary = summary or "(session completed)"
            print(f"  ℹ️  No daily memory file for {today}, using raw summary")

    result = end_session(
        session_id,
        summary=summary or "(completed)",
        what_worked=worked or [],
        what_failed=failed or [],
    )

    # Clean up marker
    if os.path.exists(sid_path):
        os.remove(sid_path)

    print(f"✅ Session {result['id']} ended for [{agent_id}]")
    print(f"   Duration: {result.get('duration_s', '?')}s")
    print(f"   Summary:  {summary[:80]}..." if summary else "   Summary:  (none)")
    print(f"   Exported: memory/sessions/session_{result['id']}.md")

    # Also add key events as notes
    if worked:
        for w in worked[:3]:
            add_note(agent_id, f"Sve: {w[:60]}", w, ["session-auto"], 1)
    if failed:
        for f_item in failed[:3]:
            add_note(agent_id, f"⚠ Blocker: {f_item[:60]}", f_item, ["session-auto", "blocker"], 3)

    return result


def cmd_status(agent_id: str):
    """Show current session and pending tasks."""
    _ensure_registered(agent_id)

    # Pending tasks
    tasks = get_pending_tasks(agent_id)
    print(f"📊 Status for [{agent_id}]")
    print(f"   Pending tasks: {len(tasks)}")
    for t in tasks:
        print(f"     • Task '{t['task_id']}' step {t['step']} → {t['status']} (retries: {t['retry_count']})")

    # Active session
    sid_path = os.path.join(BASE, "runtime", f".active_session_{agent_id}")
    if os.path.exists(sid_path):
        with open(sid_path) as f:
            sid = f.read().strip()
        print(f"   Active session: {sid}")

    # Agent info
    agent = get_agent(agent_id)
    if agent:
        print(f"   Persona: {agent['persona_file']}")

    if not tasks:
        print("   ✅ No pending tasks. All clear.")


def cmd_checkpoint(agent_id: str, task_id: str, step: int, status: str = "running"):
    """Save a workflow checkpoint."""
    _ensure_registered(agent_id)

    sid_path = os.path.join(BASE, "runtime", f".active_session_{agent_id}")
    session_id = None
    if os.path.exists(sid_path):
        with open(sid_path) as f:
            session_id = int(f.read().strip())

    cp = save_checkpoint(session_id, task_id, step, status)
    print(f"✅ Checkpoint saved: task '{task_id}' step {step} → {status}")
    print(f"   memory/checkpoints/checkpoint_{cp['id']}_{task_id}.md")
    return cp


def cmd_context(agent_id: str):
    """Print runtime prompt (for injection into OpenClaw system prompt)."""
    _ensure_registered(agent_id)

    prompt = build_runtime_prompt(agent_id)

    rt_path = os.path.join(BASE, "runtime", "runtime_prompt.md")
    os.makedirs(os.path.dirname(rt_path), exist_ok=True)
    with open(rt_path, "w") as f:
        f.write(prompt)

    print(prompt)
    print(f"\n# Written to: {rt_path}")


def cmd_search(query: str):
    """Search notes and sessions."""
    print(f"🔍 Searching for: {query}\n")

    notes = search_notes(query)
    if notes:
        print(f"── Notes ({len(notes)}) ──")
        for n in notes:
            tags = n.get("tags", "") or ""
            print(f"  [{tags}] {n['title']}")
            print(f"  {n['content'][:120]}...")
            print()

    sessions = search_sessions(query)
    if sessions:
        print(f"── Sessions ({len(sessions)}) ──")
        for s in sessions:
            print(f"  Session {s['id']} ({s['created_at'][:19]}): {s.get('summary', '')[:120]}")


def cmd_auto_daily(agent_id: str = "main"):
    """Scan daily memory files and create RAG notes from new content."""
    _ensure_registered(agent_id)

    if not os.path.isdir(MEMORY_DIR):
        print(f"  ⚠️  No memory directory at {MEMORY_DIR}")
        return

    files = sorted(os.listdir(MEMORY_DIR))
    count = 0
    for fname in files:
        if not fname.endswith(".md"):
            continue
        key = f"_{fname.replace('.md','')}"
        marker = os.path.join(BASE, "runtime", f".indexed{key}")

        if os.path.exists(marker):
            continue  # Already indexed

        path = os.path.join(MEMORY_DIR, fname)
        with open(path) as f:
            content = f.read()

        title = f"Daily Memory: {fname.replace('.md','')}"
        add_note(agent_id, title, content[:1000], ["daily-memory"], 1)
        with open(marker, "w") as f:
            f.write("1")
        count += 1
        print(f"  📝 Indexed: {fname} ({len(content)} chars)")

    if count == 0:
        print("  ✅ All daily memory files already indexed")
    else:
        print(f"  ✅ Indexed {count} new daily memory file(s)")


# ── CLI dispatch ─────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "start":
        if len(args) < 2:
            print("Usage: integrate start <agent_id> [--max-tokens <n>]")
            sys.exit(1)
        mt = 6000
        if "--max-tokens" in args:
            mt = int(args[args.index("--max-tokens") + 1])
        cmd_start(args[1], mt)

    elif cmd == "end":
        if len(args) < 2:
            print("Usage: integrate end <agent_id> [--summary '...'] [--auto]")
            sys.exit(1)
        kwargs = {"agent_id": args[1], "auto": "--auto" in args}
        i = 2
        while i < len(args):
            if args[i] == "--summary" and i + 1 < len(args):
                kwargs["summary"] = args[i + 1]
                i += 2
            elif args[i] == "--worked" and i + 1 < len(args):
                kwargs["worked"] = [x.strip() for x in args[i + 1].split(",")]
                i += 2
            elif args[i] == "--failed" and i + 1 < len(args):
                kwargs["failed"] = [x.strip() for x in args[i + 1].split(",")]
                i += 2
            else:
                i += 1
        cmd_end(**kwargs)

    elif cmd == "status":
        if len(args) < 2:
            print("Usage: integrate status <agent_id>")
            sys.exit(1)
        cmd_status(args[1])

    elif cmd == "checkpoint":
        if len(args) < 4:
            print("Usage: integrate checkpoint <agent_id> <task_id> <step> [--status <s>]")
            sys.exit(1)
        status = "running"
        if "--status" in args:
            status = args[args.index("--status") + 1]
        cmd_checkpoint(args[1], args[2], int(args[3]), status)

    elif cmd == "context":
        if len(args) < 2:
            print("Usage: integrate context <agent_id>")
            sys.exit(1)
        cmd_context(args[1])

    elif cmd == "search":
        if len(args) < 2:
            print("Usage: integrate search <query>")
            sys.exit(1)
        cmd_search(" ".join(args[1:]))

    elif cmd == "daily":
        aid = args[1] if len(args) > 1 else "main"
        cmd_auto_daily(aid)

    elif cmd == "list":
        agents = list_agents()
        print("Registered agents:")
        for a in agents:
            print(f"  {a['id']:15s} → {a['name']}")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
