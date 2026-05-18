# RAG System Architecture Decision

- **Tags**: architecture, rag
- **Created**: 2026-05-18T17:25:38Z
- **Importance**: 4

Two-level platform→agent launcher. Platforms: openclaw, pi-code (extensible). Agents: Ricchys (main), Edgy (linux-admin), Pi Code (pi-code). SQLite with FTS5, no sentence-transformers. Schema v2 with platform column.
