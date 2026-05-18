#!/usr/bin/env python3
"""
summarize_session.py — Generate a session summary from raw text via heuristics.

For V1, this is a simple template-based summarizer.
In future, you can plug in an LLM call here.

Usage:
    python summarize_session.py <agent_id> <session_id> <log_text_file>
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_agent

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    agent_id = sys.argv[1]
    session_id = sys.argv[2] if len(sys.argv) > 2 else "?"
    log_file = sys.argv[3] if len(sys.argv) > 3 else None

    agent = get_agent(agent_id)

    # If no log file, just generate an empty template
    template = f"""# Session Summary Template

Agent: {agent_id}
Session: {session_id}
{'Persona: ' + agent.get('name', '?') if agent else ''}

## Summary

(What happened this session — one paragraph)

## What Worked

- (list)

## What Failed

- (list)

## Next Steps

1. (highest priority first)

## Important Files

- (files changed / referenced)

## Tags

- agent:{agent_id}
"""

    if log_file:
        try:
            with open(log_file) as f:
                content = f.read()
            template += f"\n## Raw Log Snippet ({len(content)} chars)\n\n```\n{content[:2000]}\n```\n"

            # Save summary alongside the raw log
            out_path = log_file.replace(".md", "_summary.md")
            if out_path == log_file:
                out_path = log_file.rsplit(".", 1)[0] + "_summary.md"
            with open(out_path, "w") as f:
                f.write(template)
            print(f"[summarize] Summary template written → {out_path}")
        except FileNotFoundError:
            print(f"[summarize] Log file not found: {log_file}")

    print(template)
