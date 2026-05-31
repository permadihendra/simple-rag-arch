# Bug Fix: `--recent` and `status --notes` return empty

**Author:** Widura
**Date:** 2026-05-31
**Priority:** High
**Target:** pi-code (Edgy)

## Symptom

```bash
rag search --recent --agent widura-claw --json    # → []
rag status widura-claw --notes --json              # → notes: []
```

Both commands return empty results despite notes existing in the database:
```
DB: 68 notes total (61 pi-code, 6 widura-claw, 1 linux-admin)
FTS5: 68 entries, integrity: ok
```

## Root Cause

Both commands use `search_notes("*", limit)` to fetch recent notes. `search_notes()` performs an FTS5 MATCH query. In FTS5:

| Query | Behavior | Result |
|-------|----------|--------|
| `"testing"` | Exact word match | Works |
| `"test*"` | Prefix match (testing, tested, tests) | Works |
| `"*"` | **Empty prefix — matches nothing** | **Broken** |

A bare `*` is not a valid FTS5 query. It's a prefix operator that needs a word before it (`"word*"`), not a SQL-style wildcard.

## Files to Fix

### 1. `rag.py` — `search()` command (line ~635)

```python
# BEFORE (broken):
notes = search_notes("*", limit)

# AFTER (fixed):
import sqlite3
from scripts.db import DB_PATH
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
notes = [dict(r) for r in conn.execute(
    "SELECT id, agent_id, title, substr(content,1,200) as content, importance, created_at, "
    "(SELECT group_concat(t.name, ', ') FROM note_tags nt JOIN tags t ON t.id = nt.tag_id WHERE nt.note_id = notes.id) as tags "
    "FROM notes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
conn.close()
```

Or better, add a helper function to `scripts/db.py`:

```python
# Add to scripts/db.py
def get_recent_notes(limit=5, agent_id=None):
    """Get most recent notes, optionally filtered by agent."""
    c = _conn()
    if agent_id:
        rows = c.execute("""
            SELECT n.*, GROUP_CONCAT(t.name, ', ') as tags
            FROM notes n
            LEFT JOIN note_tags nt ON nt.note_id = n.id
            LEFT JOIN tags t ON t.id = nt.tag_id
            WHERE n.agent_id = ?
            GROUP BY n.id
            ORDER BY n.id DESC LIMIT ?
        """, (agent_id, limit)).fetchall()
    else:
        rows = c.execute("""
            SELECT n.*, GROUP_CONCAT(t.name, ', ') as tags
            FROM notes n
            LEFT JOIN note_tags nt ON nt.note_id = n.id
            LEFT JOIN tags t ON t.id = nt.tag_id
            GROUP BY n.id
            ORDER BY n.id DESC LIMIT ?
        """, (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]
```

Then `rag.py` can use:
```python
from scripts.db import get_recent_notes
notes = get_recent_notes(limit, agent)
```

### 2. `rag.py` — `status()` command (line ~564)

Same fix:

```python
# BEFORE (broken):
recent_notes = search_notes("*", 5)
entry["notes"] = [{"id": n["id"], "title": n["title"], "tags": n.get("tags", ""), "importance": n.get("importance", 0)} for n in recent_notes if n["agent_id"] == aid]

# AFTER (fixed with get_recent_notes from db.py):
recent_notes = get_recent_notes(5, aid)
entry["notes"] = [{"id": n["id"], "title": n["title"], "tags": n.get("tags", ""), "importance": n.get("importance", 0)} for n in recent_notes]
```

## Why Not Fix FTS5 Instead?

FTS5 doesn't support a "return everything" query mode. It's designed for keyword search, not browsing. Using direct SQL with `ORDER BY id DESC` is the correct approach for "recent notes" — it's faster, simpler, and actually works.

## Test Verification

```bash
# After fix, these should return data:
rag search --recent --agent widura-claw --json      # → notes with agent_id="widura-claw"
rag search --recent --agent pi-code -l 3 --json      # → notes with agent_id="pi-code"
rag status widura-claw --notes --json                 # → notes array populated
rag status --notes --json                             # → all agents with notes

# Normal keyword search should be unaffected:
rag search "vpn" --json                               # → works as before
rag search "vpn" --agent pi-code --json               # → works as before
```

## Files Summary

| File | Change |
|------|--------|
| `scripts/db.py` | Add `get_recent_notes(limit, agent_id)` function |
| `rag.py` line 564 | Replace `search_notes("*", 5)` with `get_recent_notes(5, aid)` |
| `rag.py` line 635 | Replace `search_notes("*", limit)` with `get_recent_notes(limit, agent)` |

---

*3 changes across 2 files. ~30 lines total. Ready for pickup.*
