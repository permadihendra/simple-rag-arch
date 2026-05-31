# `rag` CLI Interface — Improvement Plan (Updated 2026-05-31)

**Author:** Widura
**Date:** 2026-05-31
**Status:** P1-P5 implemented by pi-code (Edgy) — minor bugs remain
**Executor:** pi-code (Edgy)

## Motivation

The `rag` CLI is the standardized bridge for all RAG access.
Every agent uses this single interface — no inline Python, no ad-hoc workflows.

## Current CLI Surface

| Command | Usage | Notes |
|---------|-------|-------|
| `search <query>` | `--json`, `--agent`, `--limit`, `--recent` | Keyword or `--recent` |
| `note` | `--title`, `--content`, `--agent`, `--tags`, `--importance`, `--json` | Hardenend, no hang |
| `status [agent]` | Sessions + tasks | `--notes`, `--json` added |
| `list` | Registered agents `[-v]` | No counts |
| `context [agent]` | Generate runtime prompt | File + echo |
| `end` | End session | Has flags |
| `checkpoint` | Save checkpoint | Task/step/status |
| `daily` | Index memory files | Niche |

## Proposals Implemented

### ✅ P1 — `--recent` on `search`

```
rag search --recent --agent pi-code --json
```

Returns most recent notes without keyword.
**⚠ Bug:** Returns empty `[]` for both pi-code and widura-claw even when notes exist in DB.
Probable cause: `--recent` query in `retrieval_router.py` not scoped to agent filter.

---

### ✅ P2 — `--agent` as real filter

```
rag search "vpn" --agent pi-code --json
```

Results now only come from the specified agent.
Verified: agent list contains only `{'pi-code'}` when `--agent pi-code` is used.

---

### ✅ P3 — `--notes` on `status`

```
rag status widura-claw --notes --json
```

Returns structured JSON with notes array.
**⚠ Bug:** Notes array is always empty (`"notes": []`) even when DB has 6 notes for widura-claw.
Probable cause: notes query in `status` handler not wired to the DB correctly.

---

### ✅ P4 — Rename + harden `add-note-cmd`

- `rag note` exists (alias, also keeps `add-note-cmd` for compat)
- Missing `--title` or `--content` shows error + usage (no hang)
- `--json` support
- **⚠ Note:** Default `--agent` is `pi-code`, not `widura-claw`. Intentional or not?

---

### ✅ P5 — `--json` on other commands

Verified on: `note`, `status`. Works.

---

## Bugs to Fix

| Bug | Command/Area | Symptom | Root Cause | Fix Reference |
|-----|-------------|---------|------------|---------------|
| B1 | `search --recent` | Returns `[]` | `search_notes("*", limit)` — FTS5 `*` is prefix operator, not wildcard | `fix-recent-notes-empty.md` — add `get_recent_notes()` to `db.py` |
| B2 | `status --notes` | Notes empty | Same root cause: `search_notes("*", 5)` at `rag.py:564` | Same fix as B1 |
| B3 | **Plugin context injection** | Shows only "RAG Agent: Widura (widura-claw)" — no notes | Plugin's `buildRagContextString` also calls `searchNotes("*", 3)` → returns 0 | Same fix as B1 — plugin will pick up `get_recent_notes` from `db.py` |
| B4 | **`build_runtime_prompt`** | "Recent Notes: (No recent notes)" despite 69+ notes in DB | `build_runtime_prompt()` in `db.py` line 994 calls `search_notes("*", 3)` | Same fix as B1 |

### Root Cause Detail

FTS5 MATCH syntax:
- `"test*"` → matches "testing", "tested" (prefix) ✅
- `"*"` → empty prefix, matches nothing ❌
- Use direct SQL `ORDER BY id DESC` for "recent" queries, not FTS5

**Impact:** The FTS5 `*` bug cascades through 4 areas — `rag search --recent`, `rag status --notes`, plugin context injection, and `build_runtime_prompt`. All are fixed by adding `get_recent_notes()` to `scripts/db.py` and replacing the `search_notes("*", limit)` calls with direct SQL.

## Verification Results

```bash
# DB has 6 notes for widura-claw, 61 for pi-code
# But these return empty:
rag search --recent --agent widura-claw --json    # → []
rag status widura-claw --notes --json              # → notes: []

# These work:
rag search "vpn" --agent pi-code --json            # → 5 results, all pi-code
rag note -t "X" -c "Y" --agent widura-claw --json  # → saves correctly, returns JSON
rag status widura-claw --json                       # → session info OK, notes empty
```

## Implementation Notes

### `rag.py` at `~/simple-rag-arch/rag.py`
Uses `typer` for CLI and `rich` for formatting.

### Files involved:
```
rag.py                          → CLI commands
middleware/retrieval_router.py  → search + filter logic
scripts/db.py                  → any new query functions needed
```

---

*Fixes tracked here. Ready for pi-code round 2.*
