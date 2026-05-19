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


# ── Main ─────────────────────────────────────────────────────────────

def run_all():
    tests = [
        ("rag list", test_list),
        ("rag list --verbose", test_list_verbose),
        ("rag status <agent>", test_status_agent),
        ("rag status (all)", test_status_all),
    ]

    # Allow running a single test by name
    if len(sys.argv) > 1:
        target = sys.argv[1]
        tests = [(n, fn) for n, fn in tests if target in n]

    print(f"\n🔍 Running {len(tests)} CLI test(s)...\n")

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
