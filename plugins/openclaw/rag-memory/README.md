# 🧠 RAG Memory — OpenClaw Plugin

Bridges OpenClaw with the simple-rag-arch local memory system.

## What it does

- **Memory tools** callable by the agent:
  - `rag_search` — FTS5 full-text search over notes and sessions
  - `rag_note` — Save knowledge notes with tags
  - `rag_status` — Show pending tasks and registered agents
  - `rag_checkpoint` — Save/resume workflow checkpoints
- **Auto-injects RAG context** into the agent prompt before each turn (recent notes, pending tasks)
- **Auto-tracks sessions** (start on conversation open, end on close)

## Swap-ability

This plugin is fully self-contained. To **disable**:

```bash
openclaw plugins disable rag-memory
```

To **re-enable**:

```bash
openclaw plugins enable rag-memory
```

To **uninstall**:

```bash
openclaw plugins uninstall rag-memory
```

## Configuration

```bash
# Set agent identity
openclaw config set plugins.rag-memory.agentId "linux-admin"

# Disable context injection (only if you want tools without auto-context)
openclaw config set plugins.rag-memory.injectContext false

# Disable auto-save of sessions
openclaw config set plugins.rag-memory.autoSaveSessions false
```

Available agent IDs: `linux-admin`, `main`, `pi-code`, `ops`, `coder`, `research`

## Requirements

- simple-rag-arch at `~/simple-rag-arch/`
- Python venv at `~/simple-rag-arch/.venv/`
- RAG database at `~/simple-rag-arch/memory/memory.db`

## Troubleshooting

```bash
# Check plugin status
openclaw plugins inspect rag-memory

# Refresh plugin registry if not found
openclaw plugins registry --refresh

# View plugin logs
openclaw logs
```
