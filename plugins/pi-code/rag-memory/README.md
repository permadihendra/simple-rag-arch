# 🧠 RAG Memory — Pi Code Extension

Bridges Pi Code agent with the simple-rag-arch local memory system.

## What it does

- **Auto-loads RAG context** on session start (recent sessions, pending tasks, notes)
- **Injects memory into system prompt** before each turn
- **Custom tools** for LLM to search/save memory:
  - `rag_search` — FTS5 full-text search over notes and sessions
  - `rag_note` — Save knowledge notes with tags
  - `rag_status` — Show active session, pending tasks, agents
  - `rag_end_session` — End session with summary, auto-save what worked/failed
  - `rag_checkpoint` — Save/resume workflow checkpoints
  - `rag_configure` — Switch between agent identities
- **Commands**: `/rag search <query>`, `/rag status`, `/rag end`, `/rag config <agent>`
- **Auto-saves** what worked/failed as notes on session end

## Swap-ability

This extension is fully self-contained. To **disable** without removing:

```bash
# Option A: Rename to deactivate
mv ~/.pi/agent/extensions/rag-memory ~/.pi/agent/extensions/rag-memory.disabled

# Option B: Just remove the active session tracking
# (extension stays loaded but won't inject context)
```

To **re-enable**:

```bash
mv ~/.pi/agent/extensions/rag-memory.disabled ~/.pi/agent/extensions/rag-memory
```

## Configuration

Edit `~/.pi/agent/extensions/rag-memory/config.json`:

```json
{
  "agentId": "pi-code"
}
```

Available agent IDs: `pi-code`, `linux-admin`, `main`, `ops`, `coder`, `research`

## Requirements

- simple-rag-arch at `~/simple-rag-arch/`
- Python venv at `~/simple-rag-arch/.venv/`
- RAG database at `~/simple-rag-arch/memory/memory.db`
