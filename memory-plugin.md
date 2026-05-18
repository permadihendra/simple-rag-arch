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
| `rag_status` | ✅ | ✅ | Show pending tasks & agents |
| `rag_checkpoint` | ✅ | ✅ | Save/resume workflow checkpoints |
| `rag_end_session` | ✅ | ❌ | End session with summary |
| `rag_configure` | ✅ | ❌ | Switch agent identity on-the-fly |

### Auto-behaviors

| Behavior | Pi Code | OpenClaw |
|----------|---------|----------|
| Load RAG context on session start | ✅ session_start | ❌ |
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

## Adding Another Platform

1. Create `rag_search`, `rag_note`, `rag_status`, `rag_checkpoint` tools
2. Call Python backend: `~/simple-rag-arch/.venv/bin/python3 -c "..."`  
3. Wire up lifecycle hooks for context injection and session tracking
4. Add README and register in this table

## Requirements

- Python 3.12+ (via `.venv`)
- SQLite FTS5 (bundled)
- OpenClaw plugin: needs `openclaw` CLI with plugin support (2026.5.6+)
- Pi Code extension: needs `pi` with extension support
