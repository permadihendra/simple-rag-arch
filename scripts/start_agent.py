#!/usr/bin/env python3
"""
start_agent.py — Start a new agent session.

1. Auto-register agent from agents/ directory if needed
2. Start session
3. Build runtime prompt
4. Write runtime prompt to runtime/runtime_prompt.md

Usage:
    python start_agent.py <agent_id> [--max-tokens <n>] [--register]
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import auto_register_agents, register_agent, start_session, build_runtime_prompt, get_agent

if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 1 or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    agent_id = args[0]
    max_tokens = 6000
    do_register = "--register" in args or "-r" in args

    if "--max-tokens" in args:
        idx = args.index("--max-tokens")
        max_tokens = int(args[idx + 1])

    # Auto-discover agents from agents/ directory (no hardcoded map needed)
    newly_registered = auto_register_agents()

    if do_register:
        # Ensure this specific agent is registered (lazy auto-register handles it)
        agent = get_agent(agent_id)
        if agent:
            print(f"[start] Agent already registered: {agent['name']} ({agent_id})")
        else:
            print(f"[start] No persona file found for '{agent_id}' — registering with defaults")
            agent = register_agent(agent_id, agent_id.replace("-", " ").title(), f"agents/{agent_id}.md")
            print(f"[start] Registered agent: {agent['name']} ({agent_id})")

    # Start session
    session_id = start_session(agent_id)
    print(f"[start] Session {session_id} started for agent '{agent_id}'")

    # Build and write prompt
    prompt = build_runtime_prompt(agent_id, max_tokens=max_tokens)
    rt_path = os.path.expanduser("~/simple-rag-arch/runtime/runtime_prompt.md")
    os.makedirs(os.path.dirname(rt_path), exist_ok=True)
    with open(rt_path, "w") as f:
        f.write(prompt)

    print(f"[start] Runtime prompt written → {rt_path}")
    print(f"[start] Session ID: {session_id} | Ready.")

    # Save session id to a temp file for end_session.py to pick up
    sid_path = os.path.expanduser(f"~/simple-rag-arch/runtime/.active_session_{agent_id}")
    with open(sid_path, "w") as f:
        f.write(str(session_id))
