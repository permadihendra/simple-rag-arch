"""
retrieval_router.py — Retrieval Router with Confidence Scoring

Implements the priority-based retrieval chain and confidence scoring
as documented in PLAN.md (V2 — Intelligence Layer).

Priority chain:
  1. Active checkpoints  (resumable workflows — highest urgency)
  2. Recent sessions     (continuity from previous work)
  3. FTS5 keyword search (fast, deterministic, reliable)
  4. Embedding search    (future — optional)
  5. External fallback   (when local confidence is low)

For each result, confidence is scored on:
  - Exact keyword match   (+3)
  - Same agent namespace  (+2)
  - Recency (< 24h)       (+2)
  - FTS5 BM25 rank        (+1)
  - Tag overlap           (+1)

Thresholds:
  - >= 5  → HIGH   → use directly
  - 3-4   → MEDIUM → present with confidence note
  - < 3   → LOW    → trigger external fallback
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# Add scripts directory to path for db imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from db import (
    get_pending_tasks,
    get_recent_sessions,
    search_notes,
    search_sessions,
    get_agent,
)


# ── Confidence Signals ──────────────────────────────────────────────────────

SIGNAL_EXACT_MATCH = 3
SIGNAL_SAME_AGENT = 2
SIGNAL_RECENCY_24H = 2
SIGNAL_BM25_RANK = 1
SIGNAL_TAG_OVERLAP = 1

THRESHOLD_HIGH = 5
THRESHOLD_MEDIUM = 3


# Common stop words that don't indicate a meaningful match
_STOP_WORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "to", "of", "is", "it",
    "or", "and", "for", "by", "with", "as", "from", "be", "was",
    "are", "were", "been", "being", "have", "has", "had", "do",
    "does", "did", "but", "if", "so", "no", "not", "up", "out",
})


def _exact_keyword_match(query: str, text: str) -> bool:
    """Check if any meaningful keyword from query appears in text.
    Filters out common stop words to avoid false positives.
    """
    if not query or not text:
        return False
    keywords = [
        kw for kw in query.lower().split()
        if len(kw) >= 3 and kw not in _STOP_WORDS
    ]
    if not keywords:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _is_recent(timestamp_str: str, hours: int = 24) -> bool:
    """Check if a timestamp is within the last N hours."""
    if not timestamp_str:
        return False
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return ts > cutoff
    except (ValueError, TypeError):
        return False


def _compute_confidence(query: str, item: dict, agent_id: str) -> int:
    """
    Compute a confidence score for a memory item against the query.
    Returns an integer score.
    """
    score = 0

    # Signal 1: Exact keyword match (+3)
    text_fields = []
    for key in ("summary", "title", "content", "what_worked", "what_failed", "description"):
        val = item.get(key)
        if val:
            text_fields.append(str(val))
    if any(_exact_keyword_match(query, field) for field in text_fields):
        score += SIGNAL_EXACT_MATCH

    # Signal 2: Same agent namespace (+2)
    item_agent = item.get("agent_id")
    if item_agent and item_agent == agent_id:
        score += SIGNAL_SAME_AGENT

    # Signal 3: Recency within 24h (+2)
    for key in ("created_at", "updated_at", "ended_at"):
        ts = item.get(key)
        if ts and _is_recent(ts, hours=24):
            score += SIGNAL_RECENCY_24H
            break

    # Signal 4: BM25 rank from FTS5 (+1) — approximate by position
    # Items from FTS5 already come ordered by rank; the first few get a bonus
    # This is applied in _score_fts_results()

    # Signal 5: Tag overlap (+1)
    tags = item.get("tags", "")
    if tags and _exact_keyword_match(query, tags):
        score += SIGNAL_TAG_OVERLAP

    return score


def _score_fts_results(query: str, results: list[dict], agent_id: str) -> list[dict]:
    """Add confidence scores to FTS5 results, with BM25 rank bonus for early items."""
    for i, item in enumerate(results):
        base_score = _compute_confidence(query, item, agent_id)
        # BM25 bonus: first 3 results get +1 for being top-ranked
        if i < 3:
            base_score += SIGNAL_BM25_RANK
        item["_confidence"] = base_score
        item["_source"] = "fts5"
    return results


# ── Retrieval Pipeline ──────────────────────────────────────────────────────

def retrieve(
    query: str,
    agent_id: str,
    limit: int = 5,
    include_checkpoints: bool = True,
    include_sessions: bool = True,
    include_fts: bool = True,
) -> dict:
    """
    Full retrieval pipeline.

    Args:
        query: The search query from the user/agent.
        agent_id: The requesting agent's ID.
        limit: Max results to return.
        include_checkpoints: Whether to check active checkpoints.
        include_sessions: Whether to include recent sessions.
        include_fts: Whether to run FTS5 keyword search.

    Returns:
        dict with:
          - results: list of scored items (sorted by confidence desc)
          - confidence_level: "high" | "medium" | "low"
          - top_score: the highest confidence score
          - needs_external_fallback: True if confidence < THRESHOLD_MEDIUM
          - sources_checked: which sources were queried
    """
    all_results = []

    # ── Priority 1: Active checkpoints ──────────────────────────────────
    sources_checked = []
    if include_checkpoints:
        sources_checked.append("checkpoints")
        try:
            checkpoints = get_pending_tasks(agent_id)
            for cp in checkpoints:
                score = _compute_confidence(query, cp, agent_id)
                # Checkpoints get a base bonus for being priority 1
                if score < SIGNAL_EXACT_MATCH:
                    score += 1  # minimum relevance for active tasks
                all_results.append({
                    "source": "checkpoint",
                    "priority": 1,
                    "confidence": min(score, 8),  # cap at 8
                    "content": (
                        f"Task '{cp['task_id']}' step {cp['step']} "
                        f"[{cp['status']}]"
                    ),
                    "task_id": cp["task_id"],
                    "step": cp["step"],
                    "status": cp["status"],
                    "payload": cp.get("payload"),
                    "updated_at": cp.get("updated_at"),
                })
        except Exception as e:
            # Non-fatal — don't crash if checkpoints are unavailable
            pass

    # ── Priority 2: Recent sessions ─────────────────────────────────────
    if include_sessions:
        sources_checked.append("sessions")
        try:
            sessions = get_recent_sessions(agent_id, limit=5)
            for s in sessions:
                score = _compute_confidence(query, s, agent_id)
                all_results.append({
                    "source": "session",
                    "priority": 2,
                    "confidence": score,
                    "content": s.get("summary", ""),
                    "session_id": s["id"],
                    "what_worked": s.get("what_worked"),
                    "what_failed": s.get("what_failed"),
                    "created_at": s.get("created_at"),
                    "duration_s": s.get("duration_s"),
                })
        except Exception as e:
            pass

    # ── Priority 3: FTS5 keyword search (notes + sessions) ──────────────
    if include_fts:
        sources_checked.append("fts5_notes")
        sources_checked.append("fts5_sessions")
        try:
            note_results = search_notes(query, limit=5)
            note_results = _score_fts_results(query, note_results, agent_id)
            for n in note_results:
                all_results.append({
                    "source": "note",
                    "priority": 3,
                    "confidence": n["_confidence"],
                    "content": f"{n['title']}: {n['content']}",
                    "note_id": n["id"],
                    "title": n["title"],
                    "tags": n.get("tags", ""),
                    "importance": n.get("importance", 0),
                    "created_at": n.get("created_at"),
                })
        except Exception as e:
            pass

        try:
            session_results = search_sessions(query, limit=3)
            session_results = _score_fts_results(query, session_results, agent_id)
            for s in session_results:
                all_results.append({
                    "source": "session_fts",
                    "priority": 3,
                    "confidence": s["_confidence"],
                    "content": s.get("summary", ""),
                    "session_id": s["id"],
                    "agent_id": s.get("agent_id"),
                    "what_worked": s.get("what_worked"),
                    "what_failed": s.get("what_failed"),
                    "created_at": s.get("created_at"),
                })
        except Exception as e:
            pass

    # ── Sort & Rank ─────────────────────────────────────────────────────
    # Sort by: confidence desc, then priority asc
    all_results.sort(key=lambda r: (-r["confidence"], r["priority"]))

    # Deduplicate by content (keep highest confidence)
    seen = set()
    deduped = []
    for r in all_results:
        key = r["content"][:100]  # compare first 100 chars
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    all_results = deduped

    top_results = all_results[:limit]
    top_score = top_results[0]["confidence"] if top_results else 0

    # ── Determine overall confidence level ───────────────────────────────
    if top_score >= THRESHOLD_HIGH:
        confidence_level = "high"
    elif top_score >= THRESHOLD_MEDIUM:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    return {
        "results": top_results,
        "confidence_level": confidence_level,
        "top_score": top_score,
        "needs_external_fallback": top_score < THRESHOLD_MEDIUM,
        "sources_checked": sources_checked,
        "total_candidates": len(all_results),
        "query": query,
        "agent_id": agent_id,
    }


def format_retrieval_context(router_result: dict) -> str:
    """
    Format the router result into a human-readable context block
    suitable for injecting into an agent prompt.
    """
    lines = [f"── Memory Retrieval ({router_result['confidence_level'].upper()} confidence) ──"]

    if not router_result["results"]:
        lines.append("  (No relevant local memory found)")
        if router_result["needs_external_fallback"]:
            lines.append("  ⚠ Low confidence — external search recommended")
        return "\n".join(lines)

    for i, r in enumerate(router_result["results"], 1):
        source_icon = {
            "checkpoint": "🔧",
            "session": "📋",
            "session_fts": "📋",
            "note": "📝",
        }.get(r["source"], "📄")

        confidence_label = (
            "🟢" if r["confidence"] >= THRESHOLD_HIGH else
            "🟡" if r["confidence"] >= THRESHOLD_MEDIUM else
            "🔴"
        )

        lines.append(
            f"\n{i}. {source_icon} [{r['source'].upper()}] "
            f"{confidence_label} confidence={r['confidence']}"
        )
        lines.append(f"   {r['content'][:200]}")

        # Extra metadata per source type
        if r["source"] == "checkpoint":
            lines.append(f"   → Task: {r.get('task_id', '?')} step {r.get('step', '?')} ({r.get('status', '?')})")
        elif r["source"] == "note":
            tags = r.get("tags", "")
            if tags:
                lines.append(f"   → Tags: {tags}")
        elif r["source"] in ("session", "session_fts"):
            ww = r.get("what_worked")
            if ww and ww != "[]":
                lines.append(f"   → Worked: {ww[:120]}")

    if router_result["needs_external_fallback"]:
        lines.append("\n⚠ Low confidence in local results — consider external search fallback")

    return "\n".join(lines)


# ── CLI entry point (for testing) ──────────────────────────────────────────

if __name__ == "__main__":
    import json

    query = sys.argv[1] if len(sys.argv) > 1 else "login retry"
    agent_id = sys.argv[2] if len(sys.argv) > 2 else "pi-code"
    json_only = "--json" in sys.argv or "-j" in sys.argv

    result = retrieve(query, agent_id)

    if json_only:
        print(json.dumps(result, default=str))
    else:
        print(f"\nQuery: {result['query']}")
        print(f"Agent: {result['agent_id']}")
        print(f"Confidence: {result['confidence_level']} (score: {result['top_score']})")
        print(f"Sources checked: {', '.join(result['sources_checked'])}")
        print(f"Results returned: {len(result['results'])} / {result['total_candidates']} candidates")
        print(f"Needs external fallback: {result['needs_external_fallback']}")
        print()

        print(format_retrieval_context(result))
        print()

        # JSON output for programmatic use
        print("--- JSON ---")
        print(json.dumps(result, indent=2, default=str))
