"""
test_cli.py — Integration tests for the rag.py CLI.

Tests each rag command by invoking it as a subprocess and checking
exit codes and output patterns.

Usage:
    cd ~/simple-rag-arch
    .venv/bin/python3 tests/test_cli.py [test_name]
"""

import sys
import os
import subprocess
import json
from pathlib import Path

BASE = Path.home() / "simple-rag-arch"
VENV_PYTHON = BASE / ".venv" / "bin" / "python3"
RAG_CLI = BASE / "rag.py"

# ── Fixtures: ensure test data exists ───────────────────────────────

FIXTURES_SETUP = False

def ensure_fixtures():
    """
    Ensure test agents and data exist in the DB.
    This makes tests self-contained — order-independent.
    """
    global FIXTURES_SETUP
    if FIXTURES_SETUP:
        return

    # Check if DB needs fixtures
    result = subprocess.run(
        [str(VENV_PYTHON), "-c",
         "import sys; sys.path.insert(0, 'scripts'); from db import list_agents; "
         "agents = list_agents(); print(len(agents))"],
        capture_output=True, text=True, cwd=str(BASE),
    )
    agent_count = int(result.stdout.strip() or "0")

    if agent_count >= 3:
        FIXTURES_SETUP = True
        return

    # Set up fixtures
    print("  📦 Setting up test fixtures...")
    subprocess.run(
        [str(VENV_PYTHON), "-c", """
import sys; sys.path.insert(0, 'scripts')
from db import init_db, register_agent, add_note, start_session, end_session

init_db()

agents = [
    ('pi-code', 'Pi Code Agent', 'agents/pi_code_agent.md'),
    ('linux-admin', 'Edgy', 'agents/edgy_agent.md'),
    ('edge-tester', 'Edge Tester', 'agents/test.md'),
]
for aid, name, pfile in agents:
    register_agent(aid, name, pfile)

add_note('pi-code', 'Retrieval Router architecture documented',
    'Priority chain and confidence scoring for agent memory.',
    ['architecture', 'router'], 4)

add_note('pi-code', 'Checkpoint N+1 sync implemented',
    'task_id linking between checkpoints and next_steps.',
    ['checkpoint', 'nplus1', 'sync'], 3)

sid = start_session('pi-code')
end_session(sid, 'Built retrieval router and wired into CLI',
    ['Router built', 'CLI wired'], ['None'], token_count=100)
print('Fixtures ready')
"""],
        capture_output=True, text=True, cwd=str(BASE),
    )
    FIXTURES_SETUP = True


# ── Test State ───────────────────────────────────────────────────────

PASSED = 0
FAILED = 0
ERRORS = []


def run_rag(*args: str) -> subprocess.CompletedProcess:
    """Run rag.py with given args and return CompletedProcess."""
    cmd = [str(VENV_PYTHON), str(RAG_CLI)] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(BASE),
    )
    return result


def check(name: str, ok: bool, detail: str = ""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  ✅ {name}")
    else:
        FAILED += 1
        ERRORS.append((name, detail))
        print(f"  ❌ {name}: {detail}")


# ── Test 1: rag list ─────────────────────────────────────────────────

def test_list():
    """rag list — list registered agents"""
    result = run_rag("list")
    stdout = result.stdout
    stderr = result.stderr

    check("exit code 0", result.returncode == 0,
          f"got code {result.returncode}")

    check("output shows OpenClaw header", "OpenClaw" in stdout,
          f"stdout={stdout[:200]!r}")

    # Should list at least the 3 known agents
    for agent_id in ("pi-code", "linux-admin", "edge-tester"):
        check(f"output contains agent '{agent_id}'", agent_id in stdout,
              f"missing from output")

    check("no error output", stderr == "" or "Warning" in stderr or "Deprecation" in stderr,
          f"stderr={stderr[:200]!r}")


# ── Test 2: rag list --verbose ───────────────────────────────────────

def test_list_verbose():
    """rag list --verbose — detailed agent listing"""
    result = run_rag("list", "--verbose")
    stdout = result.stdout

    check("exit code 0", result.returncode == 0,
          f"got code {result.returncode}")

    check("verbose shows agent names", "OpenClaw" in stdout,
          f"stdout={stdout[:200]!r}")


# ── Test 3: rag status <agent> ───────────────────────────────────────

def test_status_agent():
    """rag status <agent> — show status for specific agent"""
    result = run_rag("status", "linux-admin")
    stdout = result.stdout

    check("exit code 0", result.returncode == 0,
          f"got code {result.returncode}")

    check("shows agent name", "Edgy" in stdout or "linux-admin" in stdout,
          f"stdout={stdout[:200]!r}")

    check("shows session status", "session" in stdout.lower(),
          f"missing session status")

    check("shows pending tasks section", "pending" in stdout.lower() or "No pending" in stdout,
          f"missing task status")


# ── Test 4: rag status (all agents) ─────────────────────────────────

def test_status_all():
    """rag status — show status for all agents"""
    result = run_rag("status")
    stdout = result.stdout

    check("exit code 0", result.returncode == 0,
          f"got code {result.returncode}")

    # Should list at least 2 agents
    agent_count = sum(1 for a in ("pi-code", "linux-admin", "edge-tester") if a in stdout)
    check(f"shows at least 2 agents", agent_count >= 2,
          f"found {agent_count} agents in output")

    check("shows pending tasks where applicable", "Task" in stdout or "No pending" in stdout,
          f"missing task status")


# ── Test 5: rag search (with results) ───────────────────────────────

def test_search_with_results():
    """rag search <query> — search with expected results"""
    result = run_rag("search", "retrieval router", "--agent", "pi-code", "--limit", "2")
    stdout = result.stdout

    check("exit code 0", result.returncode == 0,
          f"got code {result.returncode}")

    check("shows Retrieval Router header", "Retrieval Router" in stdout,
          f"stdout={stdout[:200]!r}")

    check("shows confidence level", "Confidence:" in stdout,
          f"missing confidence")

    check("shows HIGH confidence for matching query", "HIGH" in stdout,
          f"should be HIGH for known query")

    check("shows results table", "NOTE" in stdout or "📝" in stdout,
          f"missing results")

    check("shows source icons", "📝" in stdout,
          f"missing source icons")


# ── Test 6: rag search (no results) ─────────────────────────────────

def test_search_no_results():
    """rag search <query> — search with no keyword matches
    Router still returns sessions (recency+namespace signals) but confidence is not HIGH."""
    result = run_rag("search", "xyznonexistent12345", "--agent", "pi-code")
    stdout = result.stdout

    check("exit code 0", result.returncode == 0,
          f"got code {result.returncode}")

    check("shows confidence level", "Confidence:" in stdout,
          f"stdout={stdout[:200]!r}")

    # For a nonsense query, confidence should NOT be HIGH (no keyword match)
    check("confidence is not HIGH for nonsense query", "HIGH" not in stdout,
          f"should not be HIGH for unknown query")

    check("shows some results from recency/namespace", "📋" in stdout or "SESSION" in stdout,
          f"missing session results from fallback signals")


# ── Test 7: rag search (OpenClaw agent) ─────────────────────────────

def test_search_openclaw():
    """rag search works with OpenClaw platform agent (linux-admin)"""
    result = run_rag("search", "retrieval router", "--agent", "linux-admin", "--limit", "2")
    stdout = result.stdout

    check("exit code 0", result.returncode == 0,
          f"got code {result.returncode}")

    check("shows confidence level", "Confidence:" in stdout,
          f"missing confidence")

    check("returns results", "NOTE" in stdout or "📝" in stdout,
          f"missing results for linux-admin")


# ── Test 8: rag search --json ─────────────────────────────────────

def test_search_json():
    """rag search <query> --json — valid JSON output"""
    result = run_rag("search", "retrieval router", "--agent", "pi-code", "--limit", "1", "--json")
    stdout = result.stdout

    check("exit code 0", result.returncode == 0,
          f"got code {result.returncode}")

    # Extract JSON from stdout (after the rich header line)
    json_start = stdout.find("{")
    if json_start >= 0:
        json_str = stdout[json_start:]
        try:
            data = json.loads(json_str)
            check("valid JSON: has confidence_level key", "confidence_level" in data,
                  f"missing confidence_level")
            check("valid JSON: has results key", "results" in data,
                  f"missing results")
            check("valid JSON: results is a list", isinstance(data["results"], list),
                  f"results not a list")
            check("valid JSON: has sources_checked", "sources_checked" in data,
                  f"missing sources_checked")
        except json.JSONDecodeError as e:
            check(f"valid JSON parses correctly", False, f"json parse error: {e}")
    else:
        check("stdout contains JSON object", False, f"no JSON found in stdout={stdout[:200]!r}")


# ── Test 9: rag context <agent> ─────────────────────────────────────

def test_context():
    """rag context <agent> — generate runtime prompt"""
    result = run_rag("context", "linux-admin")
    stdout = result.stdout

    check("exit code 0", result.returncode == 0,
          f"got code {result.returncode}")

    check("shows context generated message", "Context generated" in stdout,
          f"stdout={stdout[:200]!r}")

    check("shows agent name in context", "Edgy" in stdout or "linux-admin" in stdout,
          f"missing agent identity")

    check("shows session section", "Recent Sessions" in stdout,
          f"missing sessions section")

    check("shows pending tasks section", "Pending Tasks" in stdout,
          f"missing pending tasks section")

    check("shows context budget", "Context Budget" in stdout,
          f"missing budget section")


# ── Test 10: rag end with no active session ────────────────────────

def test_end_no_session():
    """rag end <agent> — error when no active session.
    Uses edge-tester which should have no active session.
    Ends any lingering session first to ensure clean state."""
    # Clean up any lingering marker first
    run_rag("end", "edge-tester", "-s", "cleanup")

    result = run_rag("end", "edge-tester")

    check("exit code 1 (error)", result.returncode == 1,
          f"got code {result.returncode}")

    stdout = result.stdout
    stderr = result.stderr
    output = stdout + stderr

    check("shows no active session error", "No active session" in output,
          f"output={output[:200]!r}")


# ── Main ─────────────────────────────────────────────────────────────

def run_all():
    tests = [
        ("rag list", test_list),
        ("rag list --verbose", test_list_verbose),
        ("rag status <agent>", test_status_agent),
        ("rag status (all)", test_status_all),
        ("rag search (with results)", test_search_with_results),
        ("rag search (no results)", test_search_no_results),
        ("rag search (OpenClaw)", test_search_openclaw),
        ("rag search --json", test_search_json),
        ("rag context <agent>", test_context),
        ("rag end no session", test_end_no_session),
    ]

    # Allow running a single test by name
    if len(sys.argv) > 1:
        target = sys.argv[1]
        tests = [(n, fn) for n, fn in tests if target in n]

    print(f"\n🔍 Running {len(tests)} CLI test(s)...\n")

    ensure_fixtures()

    for name, fn in tests:
        print(f"[bold]{name}[/]" if False else f"\n── {name} ──")
        try:
            fn()
        except Exception as e:
            global FAILED
            FAILED += 1
            ERRORS.append((name, str(e)))
            print(f"  ❌ EXCEPTION: {e}")

    total = PASSED + FAILED
    print(f"\n{'='*40}")
    print(f"Results: {PASSED}/{total} passed, {FAILED} failed")
    if ERRORS:
        print(f"\nErrors:")
        for name, detail in ERRORS:
            print(f"  {name}: {detail}")
    print()

    return FAILED == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
