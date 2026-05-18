#!/usr/bin/env python3
"""
save_checkpoint.py — Save or update a workflow checkpoint.

Usage:
    python save_checkpoint.py create <task_id> <step> [--session <id>] [--status <s>] [--payload <json>]
    python save_checkpoint.py list <task_id>
    python save_checkpoint.py pending <agent_id>
"""

import sys
import json
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import save_checkpoint, get_checkpoints_for_task, get_pending_tasks

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]

    if cmd == "create":
        if len(args) < 3:
            print("Usage: save_checkpoint.py create <task_id> <step> [--session <id>] [--status <s>] [--payload <json>]")
            sys.exit(1)
        task_id = args[1]
        step = int(args[2])
        session_id = None
        status = "running"
        payload = None

        i = 3
        while i < len(args):
            if args[i] == "--session":
                session_id = int(args[i + 1])
                i += 2
            elif args[i] == "--status":
                status = args[i + 1]
                i += 2
            elif args[i] == "--payload":
                payload = json.loads(args[i + 1])
                i += 2
            else:
                i += 1

        cp = save_checkpoint(session_id, task_id, step, status, payload)
        print(f"[checkpoint] Created/updated checkpoint {cp['id']} for task '{task_id}' step {step} → {status}")
        print(json.dumps(cp, indent=2, default=str))

    elif cmd == "list":
        if len(args) < 2:
            print("Usage: save_checkpoint.py list <task_id>")
            sys.exit(1)
        cps = get_checkpoints_for_task(args[1])
        print(f"Checkpoints for task '{args[1]}':")
        for cp in cps:
            print(f"  [{cp['id']}] step {cp['step']} — {cp['status']} (retries: {cp['retry_count']})")

    elif cmd == "pending":
        if len(args) < 2:
            print("Usage: save_checkpoint.py pending <agent_id>")
            sys.exit(1)
        tasks = get_pending_tasks(args[1])
        print(f"Pending tasks for '{args[1]}':")
        for t in tasks:
            print(f"  • {t['task_id']} step {t['step']} → {t['status']} (last: {t['updated_at'][:19]})")
        if not tasks:
            print("  (none)")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
