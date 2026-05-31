# MINIMAL_RAG_ARCHITECTURE.md

# Minimal Local-First Agent Memory Architecture

## Objective

Build a lightweight persistent memory system for AI agents that:

* remembers previous sessions
* resumes interrupted workflows
* supports multiple personas
* retrieves relevant memory first
* falls back to external search when needed
* remains simple and maintainable

The system must work well on:

* OpenClaw
* Raspberry Pi
* local PCs
* low RAM environments

---

# Core Principle

This is NOT traditional chatbot RAG.

This is:

# agent memory orchestration

The goal is not:

* storing massive documents
* enterprise retrieval
* giant vector databases

The goal is:

* continuity
* workflow persistence
* intelligent retrieval
* resumable tasks

---

# Architecture Philosophy

Prioritize:

* SQLite
* explicit retrieval logic
* summaries
* checkpoints
* small high-quality context

Avoid:

* overusing embeddings
* giant prompt stuffing
* replaying full conversations
* complex frameworks too early

---

# Recommended System Architecture

```text id="3r0l6m"
User Query
    ↓
Retrieval Router
    ↓
Local Memory Search
    ↓
Confidence Check
    ↓
IF relevant:
    use local memory
ELSE:
    external search/tools
```

This is the MOST important architectural decision.

---

# Storage Design

## Primary Storage

Use:

* SQLite

Advantages:

* single file
* portable
* low RAM
* reliable
* fast enough
* Raspberry Pi friendly

---

# File Structure

```text id="0h6a49"
project/
│
├── agents/
│   ├── ops_agent.md
│   ├── coder_agent.md
│   └── research_agent.md
│
├── memory/
│   ├── memory.db
│   ├── sessions/
│   ├── notes/
│   ├── logs/
│   └── checkpoints/
│
├── plugins/
│   └── rag_plugin.py
│
├── middleware/
│   └── retrieval_router.py
│
├── commands/
│   ├── rag_search.py
│   └── rag_status.py
│
└── runtime/
    └── runtime_prompt.md
```

---

# Memory Types

## 1. Episodic Memory

Purpose:

* remember previous work
* preserve continuity

Examples:

* session summaries
* completed tasks
* blockers
* decisions

Store:

* concise summaries only

DO NOT:

* store full raw conversations

---

## 2. Procedural Memory

Purpose:

* remember workflows
* resume interrupted automation

Examples:

* browser automation state
* retry logic
* workflow checkpoints

Stored in:

* checkpoints table

---

## 3. Semantic Memory

Purpose:

* reusable knowledge
* notes
* findings
* fixes

Examples:

* Playwright retry solution
* login timeout fix
* scraping workaround

Stored as:

* markdown
* indexed in SQLite

---

# Database Schema

## sessions

```sql id="flqu2v"
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    agent_id TEXT,
    summary TEXT,
    next_steps TEXT,
    created_at DATETIME
);
```

---

## checkpoints

```sql id="v5x7tt"
CREATE TABLE checkpoints (
    id INTEGER PRIMARY KEY,
    task_id TEXT,
    step INTEGER,
    status TEXT,
    payload TEXT,
    updated_at DATETIME
);
```

---

## notes

```sql id="7zeb5z"
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    title TEXT,
    content TEXT,
    tags TEXT,
    created_at DATETIME
);
```

---

# Retrieval Strategy

# MOST IMPORTANT SECTION

The system should NOT blindly inject RAG into every prompt.

Instead:

# retrieval must be conditional

---

# Correct Retrieval Flow

## Step 1 — User Query

Example:

```text id="0u4d7v"
"how did we solve login retry issue?"
```

---

## Step 2 — Search Local Memory

Search:

* checkpoints
* session summaries
* notes
* FTS5 indexes

---

## Step 3 — Confidence Scoring

Example signals:

| Signal               | Weight   |
| -------------------- | -------- |
| exact keyword match  | high     |
| same agent namespace | medium   |
| recent memory        | medium   |
| embedding similarity | optional |

---

## Step 4 — Decision

### If confidence HIGH

Use local memory.

DO NOT perform external search.

---

### If confidence LOW

Fallback to:

* web search
* external tools
* internet retrieval

---

# Key Architectural Rule

Treat local memory like:

# L1 cache

Treat external search like:

# L2 cache

Local memory should always be checked first.

---

# Retrieval Priority Order

## Priority 1 — Active Checkpoints

Most important memory.

Examples:

* interrupted browser automation
* unfinished workflows
* failed retry states

This creates persistence.

---

## Priority 2 — Recent Session Summaries

Examples:

* what was completed
* blockers
* next actions

---

## Priority 3 — Keyword Search (FTS5)

Reliable and fast.

Prefer this before embeddings.

---

## Priority 4 — Embedding Search

Optional enhancement only.

Do NOT depend heavily on embeddings.

---

## Priority 5 — External Search

Fallback only when local memory confidence is low.

---

# Startup Context Flow

When agent starts:

Load:

* persona
* last sessions
* active tasks
* unfinished checkpoints

Build runtime context:

```text id="5n0jsw"
You are Ops Agent.

Recent sessions:
...

Active unfinished tasks:
...

Suggested continuation:
...
```

Inject into:

* OpenClaw system prompt
* Pi coding agent prompt

---

# Session Shutdown Flow

When session ends:

Generate:

* concise summary
* next actions
* blockers
* important findings

Store:

* SQLite
* optional JSON backup

DO NOT:

* dump raw chats

---

# Checkpoint System

Purpose:

* recover from crashes
* continue automation
* maintain workflow state

Example:

```json id="4syw13"
{
  "task_id": "tokopedia_input",
  "step": 143,
  "status": "failed",
  "payload": {
    "record_id": "INV-001",
    "error": "captcha"
  }
}
```

On restart:

* resume from last incomplete step

---

# Important Design Rules

## GOOD

* concise summaries
* structured checkpoints
* explicit retrieval routing
* deterministic logic
* local-first

---

## BAD

* replaying entire chats
* stuffing prompts with chunks
* giant vector databases
* overengineering early
* depending entirely on embeddings

---

# Recommended V1 Stack

## Core

* Python
* SQLite
* SQLite FTS5

## Optional Later

* sqlite-vec
* sentence-transformers
* FastAPI memory API

---

# Recommended Middleware Flow

```text id="wut1c2"
User Prompt
    ↓
retrieval_router.py
    ↓
RAG Search
    ↓
Confidence Check
    ↓
Prompt Augmentation
    ↓
LLM
```

The router decides:

* local memory
* external search
* both
* neither

NOT the LLM.

---

# Long-Term Goal

Build a persistent lightweight AI operating layer that:

* survives restarts
* survives crashes
* remembers workflows
* supports multiple agents
* stays understandable
* stays local
* stays maintainable

The primary value is:

# continuity and workflow persistence

NOT massive RAG infrastructure.
