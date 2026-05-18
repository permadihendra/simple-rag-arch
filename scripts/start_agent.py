#!/usr/bin/env python3
"""
start_agent.py — Start a new agent session.

1. Register agent if needed
2. Start session
3. Build runtime prompt
4. Write runtime prompt to runtime/runtime_prompt.md

Usage:
    python start_agent.py <agent_id> [--max-tokens <n>] [--register]
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import register_agent, start_session, build_runtime_prompt, now

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

    # Map agent IDs to known personas
    persona_map = {
        "ops": ("ops", "Ops Agent", "agents/ops_agent.md"),
        "coder": ("coder", "Coder Agent", "agents/coder_agent.md"),
        "research": ("research", "Research Agent", "agents/research_agent.md"),
    }

    if do_register and agent_id in persona_map:
        aid, name, pfile = persona_map[agent_id]
        register_agent(aid, name, pfile)
        print(f"[start] Registered agent: {name} ({aid})")

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
