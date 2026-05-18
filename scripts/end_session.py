#!/usr/bin/env python3
"""
end_session.py — End an active agent session with a summary.

Usage:
    python end_session.py <agent_id> [--summary "text"] [--worked "item1,item2"]
                          [--failed "item1,item2"] [--files "file1,file2"]
                          [--tokens <n>] [--next-steps "step1; step2"]

    python end_session.py <agent_id> --interactive   (prompt for summary)
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import end_session

def load_active_session(agent_id: str) -> int | None:
    """Read the last active session id for an agent."""
    sid_path = os.path.expanduser(f"~/simple-rag-arch/runtime/.active_session_{agent_id}")
    if os.path.exists(sid_path):
        with open(sid_path) as f:
            return int(f.read().strip())
    return None


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 1 or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    agent_id = args[0]
    session_id = load_active_session(agent_id)
    if not session_id:
        # Try to find latest session in DB
        session_id = None  # will be handled by end_session

    summary = ""
    what_worked = []
    what_failed = []
    important_files = []
    token_count = 0
    next_steps = []

    i = 1
    while i < len(args):
        if args[i] == "--summary":
            i += 1
            summary = args[i]
        elif args[i] == "--worked":
            i += 1
            what_worked = [x.strip() for x in args[i].split(",") if x.strip()]
        elif args[i] == "--failed":
            i += 1
            what_failed = [x.strip() for x in args[i].split(",") if x.strip()]
        elif args[i] == "--files":
            i += 1
            important_files = [x.strip() for x in args[i].split(",") if x.strip()]
        elif args[i] == "--tokens":
            i += 1
            token_count = int(args[i])
        elif args[i] == "--next-steps":
            i += 1
            next_steps = [x.strip() for x in args[i].split(";") if x.strip()]
        i += 1

    if not summary:
        print("⚠️  No summary provided. Use --summary to describe what happened.")
        print("   Data will still be saved.")

    try:
        result = end_session(session_id, summary, what_worked, what_failed,
                             important_files, token_count, next_steps)
        print(f"[end] Session {result['id']} finalised for '{agent_id}'")
        print(f"  Duration: {result.get('duration_s', '?')}s")
        print(f"  Tokens:   {result.get('token_count', 0)}")
        print(f"  Summary:  {result['summary'][:80]}..." if result.get('summary') else "  Summary:  (none)")

        # Clean up active session marker
        sid_path = os.path.expanduser(f"~/simple-rag-arch/runtime/.active_session_{agent_id}")
        if os.path.exists(sid_path):
            os.remove(sid_path)
    except ValueError as e:
        print(f"Error ending session: {e}")
        # Create a placeholder session
        if agent_id:
            from db import start_session, register_agent
            try:
                register_agent(agent_id, f"Agent {agent_id}", f"agents/{agent_id}_agent.md")
            except Exception:
                pass
            new_sid = start_session(agent_id)
            result = end_session(new_sid, summary, what_worked, what_failed,
                                 important_files, token_count, next_steps)
            print(f"[end] Created and finalised new session {result['id']}")
