# 🧠 RAG Memory Plugins

Two swappable plugins that bridge AI agents with the simple-rag-arch memory system.

| Platform | Type | Location | Status |
|----------|------|----------|--------|
| **Pi Code** | Extension (TypeScript) | `~/.pi/agent/extensions/rag-memory/` | ✅ Loaded |
| **OpenClaw** | Plugin (JavaScript) | `~/.openclaw/extensions/rag-memory/` | ✅ Loaded |

## Architecture

```
┌────────────────────────────────────────────────────┐
│                    AI Agent                         │
│  (Pi Code / OpenClaw)                              │
└──────────┬──────────────────────────────┬──────────┘
           │                              │
           ▼                              ▼
┌──────────────────┐           ┌──────────────────┐
│  Pi Code Ext.    │           │  OpenClaw Plugin │
│  ~/.pi/agent/    │           │  ~/.openclaw/    │
│  extensions/     │           │  extensions/     │
│  rag-memory/     │           │  rag-memory/     │
│                  │           │                  │
│  - index.ts      │           │  - index.js      │
│  - rag-bridge.ts │           │  - openclaw.     │
│  - config.json   │           │    plugin.json   │
└──────────┬───────┘           └────────┬─────────┘
           │                            │
           └──────────┬─────────────────┘
                      │  child_process → python3
                      ▼
          ┌─────────────────────┐
          │  simple-rag-arch    │
          │  ────────────────   │
          │  scripts/db.py      │
          │  memory/memory.db   │
          │  memory/notes/*.md  │
          │  memory/sessions/*  │
          └─────────────────────┘
```

Both plugins call the same Python backend (`scripts/db.py`) via `child_process`, sharing the same SQLite database.

## What Each Plugin Provides

### Tools (callable by the LLM)

| Tool | Pi Code | OpenClaw | Purpose |
|------|---------|----------|---------|
| `rag_search` | ✅ | ✅ | FTS5 search over notes & sessions |
| `rag_note` | ✅ | ✅ | Save knowledge with tags |
| `rag_status` | ✅ | ✅ | Show pending tasks, N+1 steps & agents |
| `rag_checkpoint` | ✅ | ✅ | Save/resume workflow checkpoints |
| `rag_next_step` | ✅ | ✅ | Record N+1 for resumable workflows |
| `rag_end_session` | ✅ | ❌ | End session with summary |
| `rag_configure` | ✅ | ❌ | Switch agent identity on-the-fly |

### Slash Commands (Pi Code only)

| Command | Description |
|---------|-------------|
| `/rag-search <query>` | Search memory |
| `/rag-status` | Show active session, pending tasks, N+1 |
| `/rag-note Title \| Content \| tags` | Save a note (pipe-separated) |
| `/rag-end <summary>` | End session |
| `/rag-checkpoint <task> <step> [status]` | Save checkpoint |
| `/rag-next <description> [priority]` | Set N+1 next step |
| `/rag-config <agentId>` | Switch agent identity |

## Agent Auto-Registration 🆕

Both plugins automatically discover and register new agents when a persona
file is created in `agents/`.

**How it works:**

1. You create a new `.md` persona file in `~/simple-rag-arch/agents/`
2. On next session start, the plugin scans the `agents/` directory
3. Any file with a unique `- **ID**:` metadata field gets registered in the
   SQLite `agents` table
4. The agent becomes available via `rag_configure` and appears in `rag_status`

**The agent ID comes from the file's `- **ID**:` metadata field**, NOT the
filename. This means filenames can be descriptive (e.g. `edgy_agent.md`)
while IDs stay meaningful (e.g. `linux-admin`).

**Trigger points for auto-discovery:**
| Platform | When it runs |
|----------|-------------|
| **Pi Code** | `session_start`, `rag_configure` tool, `build_context()` |
| **OpenClaw** | `register()` (plugin load), `rag_configure` tool |
| **CLI** | `python start_agent.py --register` |

**Lazy registration:** If an agent isn't in the DB but a matching persona
file exists, `get_agent()` auto-registers it on first lookup. This means
`rag_configure` to any agent ID with a persona file Just Works™.

### Example: Create a new agent

```bash
# 1. Create the persona file
cat > ~/simple-rag-arch/agents/my-assistant.md << 'EOF'
# My Assistant

- **ID**: my-assistant
- **Name**: My Assistant
- **Platform**: pi-code

## Traits
- helpful, concise, proactive

## Responsibilities
- general assistance, research, automation
EOF

# 2. (Automatic) Next session auto-registers it.
#    Or force it now:
python ~/simple-rag-arch/scripts/start_agent.py my-assistant --register

# 3. Switch to it (Pi Code):
#    Use /rag-config my-assistant
#    Or call the rag_configure tool
```

### Auto-behaviors

| Behavior | Pi Code | OpenClaw |
|----------|---------|----------|
| Auto-register agents on startup | ✅ session_start | ✅ register() |
| Inject context before each turn | ✅ before_agent_start | ✅ before_prompt_build |
| Auto-save session on end | ✅ agent_end / tools | ✅ session_end |
| Auto-save what_worked/failed as notes | ✅ | ❌ |

## Swapability

### Disable Pi Code Extension

```bash
# Remove from auto-discovery
mv ~/.pi/agent/extensions/rag-memory{,.disabled}
# Reload pi or restart
```

### Disable OpenClaw Plugin

```bash
openclaw plugins disable rag-memory
```

### Swap scripts

```bash
# Toggle Pi Code extension on/off
~/simple-rag-arch/scripts/toggle-pi-rag.sh [on|off|status]

# Toggle OpenClaw plugin on/off
~/simple-rag-arch/scripts/toggle-oc-rag.sh [on|off|status]
```

## N+1 — Next Step Tracking

Both plugins support tracking the *next* step after current work:

1. When finishing a task step, call `rag_next_step` with what should happen next
2. The step is stored in the `next_steps` table with priority and session linkage
3. `rag_status` shows all pending N+1 items at the top of every session
4. When a checkpoint succeeds, the agent is prompted to set the N+1

This ensures **resumable workflows** — even if interrupted, the next session
shows exactly what needs to happen next.

## Adding Another Platform

1. Create `rag_search`, `rag_note`, `rag_status`, `rag_checkpoint`, `rag_next_step` tools
2. Call Python backend: `~/simple-rag-arch/.venv/bin/python3 -c "..."`  
3. Wire up lifecycle hooks for context injection and session tracking
4. Add README and register in this table

## Requirements

- Python 3.12+ (via `.venv`)
- SQLite FTS5 (bundled)
- OpenClaw plugin: needs `openclaw` CLI with plugin support (2026.5.6+)
- Pi Code extension: needs `pi` with extension support
