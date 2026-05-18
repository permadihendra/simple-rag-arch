#!/usr/bin/env python3
"""
load_context.py — Load agent context and print runtime prompt.

Usage:
    python load_context.py <agent_id> [--max-tokens <n>]
    python load_context.py --list-agents
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import build_context, build_runtime_prompt, get_agent, list_agents

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--list-agents" in args or "-l" in args:
        agents = list_agents()
        print("Registered agents:")
        for a in agents:
            print(f"  {a['id']:15s} → {a['name']}")
        sys.exit(0)

    if len(args) < 1:
        print(__doc__)
        sys.exit(1)

    agent_id = args[0]
    max_tokens = 6000
    if "--max-tokens" in args:
        idx = args.index("--max-tokens")
        max_tokens = int(args[idx + 1])

    try:
        prompt = build_runtime_prompt(agent_id, max_tokens=max_tokens)
        # Also print context metadata
        ctx = build_context(agent_id, max_tokens=max_tokens)
        print(f"── Context for {agent_id} ──")
        print(f"  Agent:          {ctx['agent']['name']} ({ctx['agent']['id']})")
        print(f"  Persona file:   {ctx['agent']['persona_file']}")
        print(f"  Recent sessions:{len(ctx['recent_sessions'])}")
        print(f"  Pending tasks:  {len(ctx['pending_tasks'])}")
        print(f"  Recent notes:   {len(ctx['recent_notes'])}")
        print(f"  Token budget:   ~{ctx['token_budget_burned']} / {ctx['max_tokens']}\n")

        # Write runtime prompt to file
        rt_path = os.path.expanduser("~/simple-rag-arch/runtime/runtime_prompt.md")
        os.makedirs(os.path.dirname(rt_path), exist_ok=True)
        with open(rt_path, "w") as f:
            f.write(prompt)
        print(f"Runtime prompt written to: {rt_path}")
        print(f"\n{prompt}")

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
