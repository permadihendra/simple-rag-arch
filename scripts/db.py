"""
db.py — SQLite database initialisation for Minimal Agent Memory System

Tables:
- schema_version  — track schema migrations
- agents          — agent personas (metadata)
- sessions        — session summaries
- sessions_fts     — FTS5 full-text search over sessions
- notes           — long-term notes / memory items
- tags            — normalised tag storage
- note_tags       — many-to-many join between notes and tags
- notes_fts       — FTS5 full-text search over notes
- checkpoints     — workflow checkpoints (resumable automation)
- next_steps      — prioritised action items extracted from sessions

Dual storage policy: SQLite is source of truth.
File exports in memory/{sessions,notes,checkpoints}/ are for human readability.
"""

import sqlite3
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.path.expanduser("~/simple-rag-arch/memory/memory.db")
BASE_DIR = os.path.dirname(DB_PATH)

# ── Versioned schema ──────────────────────────────────────────────────────────

SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- 1. Version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- 2. Agents
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    persona_file TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL
);

-- 3. Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id       TEXT NOT NULL REFERENCES agents(id),
    summary        TEXT,
    what_worked    TEXT,       -- JSON array
    what_failed    TEXT,       -- JSON array
    important_files TEXT,      -- JSON array
    token_count    INTEGER DEFAULT 0,
    created_at     TEXT NOT NULL,
    ended_at       TEXT,
    duration_s     INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    summary, what_worked, what_failed, content='sessions', content_rowid='id'
);

-- 4. Notes
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT REFERENCES agents(id),
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS note_tags (
    note_id INTEGER REFERENCES notes(id) ON DELETE CASCADE,
    tag_id  INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title, content, content='notes', content_rowid='id'
);

-- 5. Checkpoints
CREATE TABLE IF NOT EXISTS checkpoints (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id),
    task_id    TEXT NOT NULL,
    step       INTEGER NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    payload    TEXT,            -- JSON blob
    retry_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 6. Next steps (normalised)
CREATE TABLE IF NOT EXISTS next_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER REFERENCES sessions(id),
    description TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL
);
"""

# ── Triggers to keep FTS in sync ────────────────────────────────────────────

FTS_TRIGGERS = """
-- Sessions FTS sync
CREATE TRIGGER IF NOT EXISTS after_sessions_insert AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, summary, what_worked, what_failed)
    VALUES (new.id, new.summary, new.what_worked, new.what_failed);
END;

CREATE TRIGGER IF NOT EXISTS after_sessions_delete AFTER DELETE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, summary, what_worked, what_failed)
    VALUES ('delete', old.id, old.summary, old.what_worked, old.what_failed);
END;

CREATE TRIGGER IF NOT EXISTS after_sessions_update AFTER UPDATE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, summary, what_worked, what_failed)
    VALUES ('delete', old.id, old.summary, old.what_worked, old.what_failed);
    INSERT INTO sessions_fts(rowid, summary, what_worked, what_failed)
    VALUES (new.id, new.summary, new.what_worked, new.what_failed);
END;

-- Notes FTS sync
CREATE TRIGGER IF NOT EXISTS after_notes_insert AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS after_notes_delete AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS after_notes_update AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO notes_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;
"""


# ── Connection helpers ───────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    """Get a writable connection with row-factory."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def now() -> str:
    """ISO-8601 timestamp in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Schema management ────────────────────────────────────────────────────────

def init_db(force: bool = False) -> bool:
    """Run schema migration. Returns True if migration ran."""
    c = _conn()
    try:
        current = c.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()[0] or 0
    except sqlite3.OperationalError:
        current = 0

    if current >= SCHEMA_VERSION and not force:
        c.close()
        return False

    # Full schema (idempotent with IF NOT EXISTS)
    c.executescript(SCHEMA_SQL + "\n" + FTS_TRIGGERS)
    c.execute(
        "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, now()),
    )
    c.commit()
    c.close()
    print(f"[db] Schema v{SCHEMA_VERSION} applied.")
    return True


def reset_db() -> None:
    """Drop everything and re-initialise (development only)."""
    c = _conn()
    c.executescript("""
        DROP TABLE IF EXISTS next_steps;
        DROP TABLE IF EXISTS checkpoints;
        DROP TABLE IF EXISTS note_tags;
        DROP TABLE IF EXISTS tags;
        DROP TABLE IF EXISTS notes_fts;
        DROP TABLE IF EXISTS notes;
        DROP TABLE IF EXISTS sessions_fts;
        DROP TABLE IF EXISTS sessions;
        DROP TABLE IF EXISTS agents;
        DROP TABLE IF EXISTS schema_version;
    """)
    c.commit()
    c.close()
    init_db()
    print("[db] DB reset complete.")


# ── Agent CRUD ───────────────────────────────────────────────────────────────

def register_agent(agent_id: str, name: str, persona_file: str) -> dict:
    """Insert or update an agent record. Returns the row."""
    c = _conn()
    c.execute(
        """INSERT INTO agents (id, name, persona_file, status, created_at)
           VALUES (?, ?, ?, 'active', ?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, persona_file=excluded.persona_file""",
        (agent_id, name, persona_file, now()),
    )
    c.commit()
    row = c.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    c.close()
    return dict(row)


def get_agent(agent_id: str) -> dict | None:
    """Get agent record by id."""
    c = _conn()
    row = c.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def list_agents() -> list[dict]:
    """List all active agents."""
    c = _conn()
    rows = c.execute("SELECT * FROM agents WHERE status='active'").fetchall()
    c.close()
    return [dict(r) for r in rows]


# ── Session CRUD ─────────────────────────────────────────────────────────────

def start_session(agent_id: str) -> int:
    """Record session start. Returns session id."""
    c = _conn()
    cur = c.execute(
        "INSERT INTO sessions (agent_id, created_at) VALUES (?, ?)",
        (agent_id, now()),
    )
    c.commit()
    sid = cur.lastrowid
    c.close()
    return sid


def end_session(session_id: int, summary: str, what_worked: list | None = None,
                what_failed: list | None = None, important_files: list | None = None,
                token_count: int = 0, next_steps: list | None = None) -> dict:
    """Finalise a session with summary and extracted data."""
    end = now()
    c = _conn()

    # Get start time to compute duration
    row = c.execute("SELECT created_at FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        c.close()
        raise ValueError(f"Session {session_id} not found")

    start_t = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
    end_t = datetime.fromisoformat(end.replace("Z", "+00:00"))
    duration_s = int((end_t - start_t).total_seconds())

    c.execute(
        """UPDATE sessions
           SET summary=?, what_worked=?, what_failed=?, important_files=?,
               token_count=?, ended_at=?, duration_s=?
           WHERE id=?""",
        (summary,
         json.dumps(what_worked or []),
         json.dumps(what_failed or []),
         json.dumps(important_files or []),
         token_count, end, duration_s,
         session_id),
    )

    # Store next steps
    if next_steps:
        now_ts = now()
        for ns in next_steps:
            desc = ns if isinstance(ns, str) else ns.get("description", str(ns))
            prio = ns.get("priority", 0) if isinstance(ns, dict) else 0
            c.execute(
                "INSERT INTO next_steps (session_id, description, priority, created_at) VALUES (?,?,?,?)",
                (session_id, desc, prio, now_ts),
            )

    c.commit()
    result = dict(c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone())
    c.close()

    # Export human-readable file
    _export_session_file(session_id, result)

    return result


def get_recent_sessions(agent_id: str, limit: int = 5) -> list[dict]:
    """Get last N sessions for an agent."""
    c = _conn()
    rows = c.execute(
        """SELECT * FROM sessions
           WHERE agent_id=? AND summary IS NOT NULL
           ORDER BY created_at DESC LIMIT ?""",
        (agent_id, limit),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


# ── Checkpoint CRUD ──────────────────────────────────────────────────────────

def save_checkpoint(session_id: int | None, task_id: str, step: int,
                    status: str = "running", payload: dict | None = None) -> dict:
    """Create or update a workflow checkpoint. Returns the checkpoint row."""
    ts = now()
    c = _conn()
    existing = c.execute(
        "SELECT * FROM checkpoints WHERE task_id=? AND step=?",
        (task_id, step),
    ).fetchone()

    if existing:
        retries = existing["retry_count"] + 1 if status == "failed" else existing["retry_count"]
        c.execute(
            """UPDATE checkpoints
               SET status=?, payload=?, retry_count=?, updated_at=?
               WHERE id=?""",
            (status, json.dumps(payload) if payload else None, retries, ts, existing["id"]),
        )
        cid = existing["id"]
    else:
        cur = c.execute(
            """INSERT INTO checkpoints (session_id, task_id, step, status, payload, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, task_id, step, status, json.dumps(payload) if payload else None, ts, ts),
        )
        cid = cur.lastrowid

    c.commit()
    row = dict(c.execute("SELECT * FROM checkpoints WHERE id=?", (cid,)).fetchone())
    c.close()

    # Export human-readable file
    _export_checkpoint_file(row)

    return row


def get_pending_tasks(agent_id: str) -> list[dict]:
    """Get all pending/running checkpoints for an agent."""
    c = _conn()
    rows = c.execute(
        """SELECT cp.* FROM checkpoints cp
           JOIN sessions s ON cp.session_id = s.id
           WHERE s.agent_id=? AND cp.status IN ('pending','running')
           ORDER BY cp.updated_at DESC""",
        (agent_id,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_checkpoints_for_task(task_id: str) -> list[dict]:
    """Get all checkpoints for a given task, ordered by step."""
    c = _conn()
    rows = c.execute(
        "SELECT * FROM checkpoints WHERE task_id=? ORDER BY step",
        (task_id,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


# ── Notes + Tags CRUD ────────────────────────────────────────────────────────

def add_note(agent_id: str, title: str, content: str,
             tags: list[str] | None = None, importance: int = 0) -> dict:
    """Create a note with optional tags. Returns the note row."""
    c = _conn()
    cur = c.execute(
        "INSERT INTO notes (agent_id, title, content, importance, created_at) VALUES (?,?,?,?,?)",
        (agent_id, title, content, importance, now()),
    )
    nid = cur.lastrowid

    if tags:
        for tag in tags:
            tag = tag.strip().lower()
            if not tag:
                continue
            c.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            tid = c.execute("SELECT id FROM tags WHERE name=?", (tag,)).fetchone()["id"]
            c.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)", (nid, tid))

    c.commit()
    row = dict(c.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone())
    c.close()

    _export_note_file(row, tags or [])
    return row


def search_notes(query: str, limit: int = 5) -> list[dict]:
    """FTS5 keyword search over notes. Falls back to LIKE."""
    c = _conn()
    try:
        rows = c.execute(
            """SELECT n.*, GROUP_CONCAT(t.name, ', ') AS tags
               FROM notes_fts f
               JOIN notes n ON n.id = f.rowid
               LEFT JOIN note_tags nt ON nt.note_id = n.id
               LEFT JOIN tags t ON t.id = nt.tag_id
               WHERE notes_fts MATCH ?
               GROUP BY n.id
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        # FTS5 syntax error → fallback to LIKE
        pattern = f"%{query}%"
        rows = c.execute(
            """SELECT n.*, GROUP_CONCAT(t.name, ', ') AS tags
               FROM notes n
               LEFT JOIN note_tags nt ON nt.note_id = n.id
               LEFT JOIN tags t ON t.id = nt.tag_id
               WHERE n.title LIKE ? OR n.content LIKE ?
               GROUP BY n.id
               LIMIT ?""",
            (pattern, pattern, limit),
        ).fetchall()

    c.close()
    return [dict(r) for r in rows]


def search_sessions(query: str, limit: int = 5) -> list[dict]:
    """FTS5 keyword search over sessions. Falls back to LIKE."""
    c = _conn()
    try:
        rows = c.execute(
            """SELECT s.* FROM sessions_fts f
               JOIN sessions s ON s.id = f.rowid
               WHERE sessions_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        pattern = f"%{query}%"
        rows = c.execute(
            """SELECT * FROM sessions
               WHERE summary LIKE ? OR what_worked LIKE ? OR what_failed LIKE ?
               LIMIT ?""",
            (pattern, pattern, pattern, limit),
        ).fetchall()

    c.close()
    return [dict(r) for r in rows]


# ── Runtime prompt builder ───────────────────────────────────────────────────

def build_context(agent_id: str, max_tokens: int = 6000) -> dict:
    """
    Build agent startup context.

    Returns a dict with:
      - agent:      agent record
      - recent:     last 5 sessions (summarised)
      - pending:    unfinished checkpoints
      - notes:      top recent notes
      - token_budget_burned: estimated tokens in context
    """
    agent = get_agent(agent_id)
    if not agent:
        raise ValueError(f"Agent '{agent_id}' not found in DB. Register first.")

    recent = get_recent_sessions(agent_id, limit=5)
    pending = get_pending_tasks(agent_id)
    notes_rows = search_notes("*", limit=5) if recent else []

    # Rough token estimate: 1 token ≈ 4 chars
    total_chars = len(str(agent)) + sum(len(str(s)) for s in recent) + \
                  sum(len(str(p)) for p in pending) + sum(len(str(n)) for n in notes_rows)
    budget_burned = total_chars // 4

    return {
        "agent": agent,
        "recent_sessions": recent,
        "pending_tasks": pending,
        "recent_notes": notes_rows,
        "token_budget_burned": budget_burned,
        "max_tokens": max_tokens,
    }


def build_runtime_prompt(agent_id: str, max_tokens: int = 6000) -> str:
    """
    Build a ready-to-inject runtime prompt for the agent.
    Returns the prompt text.
    """
    import textwrap
    ctx = build_context(agent_id, max_tokens=max_tokens)
    agent = ctx["agent"]
    lines = [f"""You are {agent['name']} (agent_id: {agent['id']}).

── Recent Sessions ──"""]
    if ctx["recent_sessions"]:
        for s in ctx["recent_sessions"]:
            lines.append(f"\n## Session {s['id']} ({s['created_at'][:19]})\n"
                         f"  Summary: {s['summary'] or '(no summary)'}\n"
                         f"  What worked: {s.get('what_worked') or '—'}\n"
                         f"  Duration: {s.get('duration_s', '?')}s")
    else:
        lines.append("  (No recent sessions)")

    lines.append("\n── Pending Tasks ──")
    if ctx["pending_tasks"]:
        for p in ctx["pending_tasks"]:
            lines.append(f"  • Task {p['task_id']} step {p['step']} → {p['status']}")
    else:
        lines.append("  (No pending tasks)")

    lines.append("\n── Recent Notes ──")
    if ctx["recent_notes"]:
        for n in ctx["recent_notes"]:
            lines.append(f"  • [{n.get('tags', 'untagged')}] {n['title']}")
    else:
        lines.append("  (No recent notes)")

    budget = ctx["token_budget_burned"]
    pct = int((budget / max_tokens) * 100) if max_tokens else 0
    lines.append(f"\n── Context Budget ──")
    lines.append(f"  ~{budget} tokens used ({pct}% of {max_tokens} budget)")

    return "\n".join(lines)


# ── File exports (human-readable backups) ───────────────────────────────────

def _export_session_file(sid: int, data: dict) -> None:
    """Write a readable markdown file for a session."""
    out_dir = Path(BASE_DIR) / "sessions"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"session_{sid}.md"
    path.write_text(
        f"# Session {sid}\n\n"
        f"- **Agent**: {data.get('agent_id', '?')}\n"
        f"- **Created**: {data['created_at']}\n"
        f"- **Ended**: {data.get('ended_at', '—')}\n"
        f"- **Duration**: {data.get('duration_s', '?')}s\n"
        f"- **Tokens**: {data.get('token_count', 0)}\n\n"
        f"## Summary\n\n{data.get('summary', '')}\n\n"
        f"## What Worked\n\n{data.get('what_worked', '[]')}\n\n"
        f"## What Failed\n\n{data.get('what_failed', '[]')}\n\n"
        f"## Important Files\n\n{data.get('important_files', '[]')}\n"
    )


def _export_checkpoint_file(data: dict) -> None:
    """Write a readable markdown file for a checkpoint."""
    out_dir = Path(BASE_DIR) / "checkpoints"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"checkpoint_{data['id']}_{data['task_id']}.md"
    path.write_text(
        f"# Checkpoint {data['id']} — {data['task_id']}\n\n"
        f"- **Step**: {data['step']}\n"
        f"- **Status**: {data['status']}\n"
        f"- **Retries**: {data['retry_count']}\n"
        f"- **Session**: {data.get('session_id', '—')}\n"
        f"- **Updated**: {data['updated_at']}\n\n"
        f"## Payload\n\n```json\n{data.get('payload', 'null')}\n```\n"
    )


def _export_note_file(data: dict, tags: list[str]) -> None:
    """Write a readable markdown file for a note."""
    out_dir = Path(BASE_DIR) / "notes"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"note_{data['id']}.md"
    path.write_text(
        f"# {data['title']}\n\n"
        f"- **Tags**: {', '.join(tags) if tags else '—'}\n"
        f"- **Created**: {data['created_at']}\n"
        f"- **Importance**: {data['importance']}\n\n"
        f"{data['content']}\n"
    )


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"

    if cmd == "init":
        init_db()
        print(f"[db] Database ready at {DB_PATH}")
    elif cmd == "reset":
        reset_db()
    elif cmd == "status":
        c = _conn()
        tables = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print("Tables:")
        for t in tables:
            cnt = c.execute(f"SELECT COUNT(*) FROM \"{t['name']}\"").fetchone()[0]
            print(f"  {t['name']}: {cnt} rows")
        c.close()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python db.py [init|reset|status]")
