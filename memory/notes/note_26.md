# RAG Launcher Design

- **Tags**: launcher, cli
- **Created**: 2026-05-18T17:25:38Z
- **Importance**: 3

rag CLI tool using Typer + Rich. Two-level menu: platform → agent. os.execvp to auto-launch the tool after context setup. Context prompt with token budget at runtime/runtime_prompt.md. Checkpoints for workflow resume, FTS5 search for knowledge retrieval.
