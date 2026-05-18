# PLAN.md — Minimal Agent Memory System (V1)

## Objective

Build a lightweight local memory system for multiple AI agents.

The system must provide:

1. Persistent memory between sessions
2. Persona-based agents
3. Session summaries
4. Workflow checkpoints
5. Simple retrieval (FTS5)
6. Resumable automation tasks
7. Shared memory across OpenClaw / Pi Agent / future tools

The system must remain:

- simple
- local-first
- SQLite-based
- low RAM usage (~50MB)
- easy to debug
- human-readable

---

## Core Philosophy

**Do NOT build:**

- enterprise RAG
- distributed systems
- cloud vector databases
- massive LangGraph workflows
- sentence-transformers (V1 — optional later)

**Build:**

- reliable persistence
- good summaries
- resumable workflows
- minimal retrieval (FTS5, not vectors)

Memory quality > infrastructure complexity.

---

## File Migration Strategy

OpenClaw's default directory has 8 config/memory files.
The RAG system manages the dynamic ones:

| File | Decision | Rationale |
|------|----------|-----------|
| `AGENTS.md` | 🏠 **STAY** | OS-level config, injected every session |
| `SOUL.md` | 🏠 **STAY** | Personality, needed every reply |
| `IDENTITY.md` | 🏠 **STAY** | Static, tiny, never changes |
| `HEARTBEAT.md` | 🏠 **STAY** | OpenClaw runtime mechanism |
| `MEMORY.md` | 📦 **→ RAG** | Grows forever, only relevant parts needed |
| `WORKFLOW.md` | 📦 **→ RAG** | Dynamic patterns, retrieved on demand |
| `USER.md` | ⚠️ **SPLIT** | Static profile stays, project context moves to RAG |
| `TOOLS.md` | 🔗 **KEEP + INDEX** | Loaded directly + indexed for cross-agent |

---

## Architecture (V1 Implemented)

```text
~/simple-rag-arch/
│
├── PLAN.md                         ← This file
├── CHECKPOINT.md                   ← Progress tracker
│
├── agents/                         ← Agent personas (markdown)
│   ├── ops_agent.md
│   ├── coder_agent.md
│   └── research_agent.md
│
├── memory/
│   ├── memory.db                   ← Single SQLite DB (source of truth)
│   ├── sessions/                   ← Human-readable .md exports
│   ├── notes/                      ← Human-readable .md exports
│   ├── checkpoints/                ← Human-readable .md exports
│   └── logs/                       ← Raw session logs (optional)
│
├── scripts/
│   ├── db.py                       ← Schema, CRUD, FTS5, context builder
│   ├── start_agent.py              ← Register agent + start session
│   ├── end_session.py              ← Summarise + store session
│   ├── save_checkpoint.py          ← Create/update/resume checkpoints
│   ├── load_context.py             ← Build runtime prompt
│   └── summarize_session.py        ← Summary template generator
│
└── runtime/
    └── runtime_prompt.md           ← Generated startup context prompt
```

---

## Technology Stack (V1)

**Required:**
- Python 3.12+
- SQLite (stdlib `sqlite3`)
- SQLite FTS5 (bundled with Python 3.12+)

**NOT Required (V1):**
- sentence-transformers ❌ (too heavy for Pi)
- sqlite-vec ❌ (future)
- FastAPI ❌ (future)
- embeddings ❌ (future)

---

## Database Schema (V1)

```sql
-- Version tracking
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Agents (metadata for personas)
CREATE TABLE agents (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    persona_file TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL
);

-- Sessions (summaries, not full chats)
CREATE TABLE sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id       TEXT NOT NULL REFERENCES agents(id),
    summary        TEXT,
    what_worked    TEXT,         -- JSON array
    what_failed    TEXT,         -- JSON array
    important_files TEXT,        -- JSON array
    token_count    INTEGER DEFAULT 0,
    created_at     TEXT NOT NULL,
    ended_at       TEXT,
    duration_s     INTEGER
);

-- FTS5 for session search
CREATE VIRTUAL TABLE sessions_fts USING fts5(
    summary, what_worked, what_failed,
    content='sessions', content_rowid='id'
);

-- Notes (learnings, fixes, discoveries)
CREATE TABLE notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT REFERENCES agents(id),
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    importance INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Normalised tags (not comma-separated!)
CREATE TABLE tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
CREATE TABLE note_tags (
    note_id INTEGER REFERENCES notes(id) ON DELETE CASCADE,
    tag_id  INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE VIRTUAL TABLE notes_fts USING fts5(
    title, content,
    content='notes', content_rowid='id'
);

-- Workflow checkpoints (resume from crashes)
CREATE TABLE checkpoints (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id),
    task_id    TEXT NOT NULL,
    step       INTEGER NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending|running|success|failed
    payload    TEXT,             -- JSON blob
    retry_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Normalised next steps with priority
CREATE TABLE next_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER REFERENCES sessions(id),
    description TEXT NOT NULL,
    priority    INTEGER DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL
);
```

---

## V1 Features (All Implemented)

### 1. Agent Personas ✅
- 3 personas created: ops, coder, research
- Each has: identity, behavior, goals, communication style
- Stored as markdown in `agents/`
- Referenced by `agents` table in SQLite

### 2. Session Summaries ✅
- `start_session(agent_id)` → returns session id
- `end_session(id, summary, ...)` → stores + exports .md
- Extracts: what_worked, what_failed, important_files, next_steps
- **Stores only summaries, not full chat logs**

### 3. Startup Context Loading ✅
- `build_context(agent_id)` → agent + recent sessions + pending tasks + notes
- `build_runtime_prompt(agent_id)` → ready-to-inject prompt text
- Writes to `runtime/runtime_prompt.md`
- Includes token budget tracking (~4 chars = 1 token)

### 4. Workflow Checkpoints ✅
- `save_checkpoint(session_id, task_id, step, status, payload)`
- Statuses: pending → running → success/failed
- Tracks `retry_count` on failed checkpoints
- Links to session_id for traceability
- `get_pending_tasks(agent_id)` → resume from last known state

### 5. Notes + Retrieval ✅
- `add_note(agent_id, title, content, tags, importance)`
- Normalised tags (separate `tags` + `note_tags` tables)
- FTS5 full-text search: `search_notes(query)` and `search_sessions(query)`
- Graceful fallback to `LIKE` when FTS5 syntax errors

### 6. File Exports ✅
- SQLite is **source of truth**
- Human-readable `.md` files exported to `memory/sessions/`, `memory/notes/`, `memory/checkpoints/`
- Dual storage without sync complexity (exports are write-only)

---

## Startup Flow

```bash
# Register agent (one-time)
python scripts/start_agent.py ops --register

# Start session
python scripts/start_agent.py ops

# During work — save checkpoints
python scripts/save_checkpoint.py create scrape-data 1 --session 1 --status running
python scripts/save_checkpoint.py create scrape-data 2 --status success

# End session
python scripts/end_session.py ops \
  --summary "Successfully scraped 100 pages" \
  --worked "Puppeteer stable, selector fallback works" \
  --failed "Rate limiting on page 3" \
  --next-steps "Add retry delay; Export to CSV"

# Load context (for startup/continuity)
python scripts/load_context.py ops
```

---

## Context Budget Rule

When building the runtime prompt:
1. Calculate token cost of each component
2. Fill in order: persona → pending tasks → last sessions → recent notes
3. Stop at 60% of model context window
4. Report total budget burned in prompt

This prevents context overflow regardless of how many sessions accumulate.

---

## V1 Success Criteria ✅

| Criterion | Status |
|-----------|--------|
| Agent remembers previous work | ✅ FTS5 search + last 5 sessions |
| Interrupted automation can resume | ✅ Checkpoint system with retry |
| Agent startup feels continuous | ✅ Context loader + runtime prompt |
| Memory retrieval is fast | ✅ FTS5, <1ms queries |
| Runs on Raspberry Pi | ✅ stdlib only, no heavy deps |
| SQLite file is portable | ✅ Single file, 5KB for test data |

---

## Development Priority (Revised)

| Phase | Scope | Status |
|-------|-------|--------|
| **1** | Schema + agents + personas | ✅ **DONE** |
| **1b** | Startup loader + runtime prompt | ✅ **DONE** |
| **2** | Checkpoint system + session CRUD | ✅ **DONE** (merged into Phase 1) |
| **3** | FTS5 search + notes + tags | ✅ **DONE** (merged into Phase 1) |
| **4** | Context budget calculator | ✅ **DONE** |
| **5** | File exports | ✅ **DONE** |
| — | **Integration tests** | 🔜 Next |
| — | **OpenClaw integration** | 🔜 Next |
| — | sqlite-vec embeddings | Future |

---

## Future Expansion (NOT V1)

- sqlite-vec semantic search
- FastAPI memory API
- Telegram integration
- Multi-device sync (Tailscale)
- Background summarization
- Automatic note extraction from sessions
- Memory scoring / importance decay
- Cross-agent task prioritization

---

## Final Goal ✅

A lightweight persistent AI memory layer that:

- ✅ survives sessions
- ✅ survives crashes (checkpoints)
- ✅ supports multiple agents
- ✅ resumes workflows
- ✅ stays simple
- ✅ stays local
- ✅ avoids overengineering
