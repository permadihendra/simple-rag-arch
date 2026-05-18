# N+1 Next Step Tracking for Resumable Workflows

- **Tags**: feature, n+1, checkpoint, workflow
- **Created**: 2026-05-18T18:06:25Z
- **Importance**: 4

Added N+1 tracking: rag_next_step tool and /rag-next command. When finishing a task step, the LLM records what should happen next. This shows up in rag_status and the runtime prompt so work is always resumable. Uses the next_steps table with priority and session linkage.
