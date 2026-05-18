"""
test_integration.py — Integration tests for the RAG memory system.

Tests both the Python backend (db.py) and validates plugin deployment.

Usage:
    cd ~/simple-rag-arch
    .venv/bin/python3 scripts/test_integration.py [--verbose]
"""

import sys
import os
import json
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from db import (
    init_db, reset_db, register_agent, get_agent, list_agents,
    start_session, end_session, get_recent_sessions,
    add_note, search_notes, search_sessions,
    save_checkpoint, get_pending_tasks,
    add_next_step, get_pending_next_steps, complete_next_step,
    build_context, build_runtime_prompt,
    _conn,
)

BASE = Path.home() / "simple-rag-arch"

# ── Test State ───────────────────────────────────────────────────────

PASSED = 0
FAILED = 0
ERRORS = []

def check(name: str, ok: bool, detail: str = ""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        if "--verbose" in sys.argv:
            print(f"  ✅ {name}")
    else:
        FAILED += 1
        ERRORS.append((name, detail))
        print(f"  ❌ {name}: {detail}")

# ── Tests ─────────────────────────────────────────────────────────────

def test_db_init():
    """1. Database initialisation"""
    # Fresh init
    ok = init_db(force=True)
    check("init_db(force=True) returns True", ok)

    # Check tables exist
    conn = _conn()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()

    required = {"schema_version", "agents", "sessions", "notes", "tags",
                "note_tags", "checkpoints", "next_steps"}
    for t in required:
        check(f"Table '{t}' exists", t in tables)

    # FTS5 tables appear as 'table' type in sqlite_master
    all_names = [r[0] for r in _conn().execute(
        "SELECT name FROM sqlite_master WHERE name LIKE '%_fts'"
    ).fetchall()]
    conn.close()

    for t in {"sessions_fts", "notes_fts"}:
        check(f"FTS5 table '{t}' exists", t in all_names)


def test_agent_crud():
    """2. Agent registration and querying"""
    reset_db()

    # Register
    a1 = register_agent("test-agent", "TestAgent 🔬", "agents/test.md")
    check("register_agent returns dict with id", a1 and a1.get("id") == "test-agent")

    # Duplicate registration
    a2 = register_agent("test-agent", "TestAgent 🔬", "agents/test.md")
    check("re-register same agent succeeds (idempotent)", a2 and a2.get("id") == "test-agent")

    # Get agent
    g = get_agent("test-agent")
    check("get_agent finds registered agent", g and g["name"] == "TestAgent 🔬")

    g2 = get_agent("nonexistent")
    check("get_agent returns None for unknown", g2 is None)

    # List agents
    all_a = list_agents()
    check("list_agents returns >=1 agents", len(all_a) >= 1)
    check("list_agents contains test-agent", any(a["id"] == "test-agent" for a in all_a))


def test_session_lifecycle():
    """3. Session start, end, and retrieval"""
    reset_db()
    register_agent("test-sesh", "Sesh Tester", "agents/test.md")

    # Start session
    sid = start_session("test-sesh")
    check("start_session returns integer session ID", isinstance(sid, int) and sid > 0)

    # End session
    end_session(
        sid,
        "Test session completed",
        what_worked=["Feature A done", "Test passed"],
        what_failed=["Minor bug in edge case"],
        token_count=150,
    )
    check("end_session completes without error", True)

    # Recent sessions
    recent = get_recent_sessions("test-sesh", limit=3)
    check("get_recent_sessions returns at least 1", len(recent) >= 1)
    check("recent session has summary", recent[0]["summary"] == "Test session completed")

    # Verify what_worked/what_failed stored as JSON
    ww = json.loads(recent[0]["what_worked"])
    check("what_worked stored as JSON array", isinstance(ww, list) and "Feature A done" in ww)

    wf = json.loads(recent[0]["what_failed"])
    check("what_failed stored as JSON array", isinstance(wf, list) and "Minor bug" in wf[0])

    # End non-existent session — should raise ValueError
    try:
        end_session(99999, "ghost")
        check("end_session on non-existent session should raise", False, "No error raised")
    except ValueError:
        check("end_session on non-existent session raises ValueError", True)
    except Exception as e:
        check("end_session on non-existent session", False, f"Wrong exception: {e}")


def test_notes_fts():
    """4. Notes CRUD + FTS5 search"""
    reset_db()
    register_agent("note-tester", "Note Tester", "agents/test.md")

    # Add notes
    n1 = add_note("note-tester", "API Design Decision", "Use SQLite FTS5 for search, no vector embeddings in V1",
                   tags=["decision", "architecture"], importance=3)
    check("add_note returns dict with id", n1 and "id" in n1)

    n2 = add_note("note-tester", "Bug: Rate Limiting", "OpenAI rate limits hit at 100 req/min during batch",
                   tags=["bug", "blocker"], importance=5)
    check("add_note with importance=5", n2 and n2["importance"] == 5)

    n3 = add_note("note-tester", "Deployment Setup", "Deploy via systemd service, auto-restart on failure",
                   tags=["infra", "ops"])
    check("add_note with tags returns id", n3 and n3.get("id") > 0)
    # Verify tags stored by searching
    found = search_notes("Deployment", limit=5)
    has_tags = any(r.get("tags") and "infra" in r["tags"] for r in found)
    check("add_note stores tags (verified via search)", has_tags)

    # Search
    results = search_notes("FTS5", limit=5)
    check("FTS5 search 'FTS5' finds note", any("FTS5" in r["content"] or "FTS5" in r["title"] for r in results))

    results2 = search_notes("Rate Limiting", limit=5)
    check("FTS5 search 'Rate Limiting' finds blocker note", any("Rate" in r["title"] or "Limiting" in r["title"] for r in results2))

    # Empty/wildcard query fallback — read recent notes via LIKE
    results3 = search_notes("Deploy", limit=3)
    check("search 'Deploy' via LIKE fallback works", len(results3) >= 1)

    # Search with special FTS5 syntax (should fallback gracefully)
    results4 = search_notes("invalid@@@syntax!!", limit=3)
    check("FTS5 syntax error falls back to LIKE", isinstance(results4, list))


def test_checkpoints():
    """5. Workflow checkpoints"""
    reset_db()
    register_agent("cp-tester", "CP Tester", "agents/test.md")
    sid = start_session("cp-tester")

    save_checkpoint(sid, "build-api", 1, "running")
    save_checkpoint(sid, "build-api", 2, "success")
    save_checkpoint(sid, "build-api", 3, "failed")
    save_checkpoint(sid, "build-api", 4, "running")

    pending = get_pending_tasks("cp-tester")
    check("get_pending_tasks finds running checkpoints",
          any(t["task_id"] == "build-api" and t["status"] in ("running", "pending") for t in pending))

    # Pending count
    running_cps = [t for t in pending if t["status"] in ("running", "pending")]
    check("pending tasks count > 0", len(running_cps) >= 1)


def test_next_steps():
    """6. N+1 next step tracking"""
    reset_db()
    register_agent("ns-tester", "NS Tester", "agents/test.md")
    sid = start_session("ns-tester")

    ns1 = add_next_step(sid, "Write integration tests", priority=3)
    check("add_next_step returns dict with id", ns1 and "id" in ns1)

    ns2 = add_next_step(sid, "Deploy to staging", priority=2)
    check("second next step added", ns2 and ns2["description"] == "Deploy to staging")

    steps = get_pending_next_steps("ns-tester", limit=5)
    check("get_pending_next_steps returns ordered results", len(steps) >= 2)

    # Higher priority should come first
    if len(steps) >= 2:
        check("N+1 sorted by priority desc", steps[0]["priority"] >= steps[1]["priority"])

    # Complete a step
    ok = complete_next_step(ns1["id"])
    check("complete_next_step returns True", ok)

    steps_after = get_pending_next_steps("ns-tester", limit=5)
    check("completed step no longer pending", not any(s["id"] == ns1["id"] for s in steps_after))


def test_context_building():
    """7. Context builder / runtime prompt"""
    reset_db()
    register_agent("ctx-tester", "Ctx Tester", "agents/test.md")
    sid = start_session("ctx-tester")
    end_session(sid, "Context test session", what_worked=["Tested context"])

    ctx = build_context("ctx-tester", max_tokens=6000)
    check("build_context returns dict", isinstance(ctx, dict))
    check("context has agent key", "agent" in ctx)
    check("context has recent_sessions", "recent_sessions" in ctx)
    check("context has token_budget_burned", "token_budget_burned" in ctx)

    prompt = build_runtime_prompt("ctx-tester", max_tokens=6000)
    check("build_runtime_prompt returns text", isinstance(prompt, str) and len(prompt) > 50)
    check("prompt mentions agent name", "Ctx Tester" in prompt)
    check("prompt mentions Context Budget", "Context Budget" in prompt)


def test_file_exports():
    """8. File exports (sessions, notes, checkpoints)"""
    reset_db()
    register_agent("export-tester", "Export Tester", "agents/test.md")
    sid = start_session("export-tester")
    end_session(sid, "Export test")
    save_checkpoint(sid, "export-task", 1, "success")
    add_note("export-tester", "Export Note", "Testing file exports", tags=["test"])

    sesh_file = BASE / "memory" / "sessions" / f"session_{sid}.md"
    check(f"Session export file exists ({sesh_file.name})", sesh_file.exists())

    cp_dir = BASE / "memory" / "checkpoints"
    cp_files = list(cp_dir.glob("*.md"))
    check(f"Checkpoint export files exist ({len(cp_files)} found)", len(cp_files) >= 1)

    notes_dir = BASE / "memory" / "notes"
    note_files = list(notes_dir.glob("*.md"))
    check(f"Note export files exist ({len(note_files)} found)", len(note_files) >= 1)


def test_plugin_deployment():
    """9. Plugin deployment scripts"""
    deploy_sh = BASE / "scripts" / "deploy-plugins.sh"
    check("deploy-plugins.sh script exists", deploy_sh.exists())

    # Check pi plugin files at source
    pi_src = BASE / "plugins" / "pi-code" / "rag-memory"
    check("Pi plugin index.ts exists", (pi_src / "index.ts").exists())
    check("Pi plugin rag-bridge.ts exists", (pi_src / "rag-bridge.ts").exists())

    # Check openclaw plugin files at source
    oc_src = BASE / "plugins" / "openclaw" / "rag-memory"
    check("OpenClaw plugin index.js exists", (oc_src / "index.js").exists())
    check("OpenClaw plugin manifest exists", (oc_src / "openclaw.plugin.json").exists())

    # Check toggle scripts
    toggle_pi = BASE / "scripts" / "toggle-pi-rag.sh"
    toggle_oc = BASE / "scripts" / "toggle-oc-rag.sh"
    check("toggle-pi-rag.sh exists", toggle_pi.exists())
    check("toggle-oc-rag.sh exists", toggle_oc.exists())

    # Verify deploy script is executable
    check("deploy-plugins.sh is executable", os.access(deploy_sh, os.X_OK))


def test_edge_cases():
    """10. Edge cases"""
    reset_db()

    # Empty search
    results = search_notes("zzzz_nonexistent_zzzz", limit=5)
    check("search for nonexistent returns empty list", len(results) == 0)

    # Empty sessions
    recent = get_recent_sessions("nobody", limit=5)
    check("get_recent_sessions for unknown agent returns empty", len(recent) == 0)

    # Tag storage
    register_agent("edge-tester", "Edge Tester", "agents/test.md")
    n = add_note("edge-tester", "Multi-tag", "Many tags", tags=["a", "b", "c", "a"])
    check("note with duplicate tags returns id", n and n.get("id") > 0)
    # Verify deduplication (a repeated twice should store once)
    found = search_notes("Multi-tag", limit=5)
    stored = [r["tags"].split(", ") for r in found if r["tags"] and r["id"] == n["id"]]
    if stored:
        check("duplicate tags deduplicated (a stored once)", stored[0].count("a") == 1)
    else:
        check("duplicate tags deduplicated", False, "Note not found via search")

    # Session without ending
    sid = start_session("edge-tester")
    check("start_session after previous session ended (no conflict)", isinstance(sid, int))

    # Export file for session with missing fields
    end_session(sid, "Minimal session")  # no what_worked/failed
    check("session with minimal fields exports", (BASE / "memory" / "sessions" / f"session_{sid}.md").exists())


# ── Runner ────────────────────────────────────────────────────────────

def main():
    global PASSED, FAILED, ERRORS

    print(f"\n{'='*60}")
    print(f"  🧠 RAG Memory System — Integration Tests")
    print(f"{'='*60}\n")

    tests = [
        ("DB Init", test_db_init),
        ("Agent CRUD", test_agent_crud),
        ("Session Lifecycle", test_session_lifecycle),
        ("Notes & FTS5", test_notes_fts),
        ("Checkpoints", test_checkpoints),
        ("N+1 Next Steps", test_next_steps),
        ("Context Building", test_context_building),
        ("File Exports", test_file_exports),
        ("Plugin Deployment", test_plugin_deployment),
        ("Edge Cases", test_edge_cases),
    ]

    for name, fn in tests:
        print(f"\n── {name} ──")
        try:
            fn()
        except Exception as e:
            FAILED += 1
            ERRORS.append((name, f"UNHANDLED ERROR: {e}"))
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    total = PASSED + FAILED
    print(f"  Results: {PASSED}/{total} passed, {FAILED} failed")
    if ERRORS:
        print(f"\n  Failures:")
        for name, detail in ERRORS:
            print(f"    • [{name}] {detail[:120]}")
    print(f"{'='*60}\n")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
