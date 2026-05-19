/**
 * RAG Memory — OpenClaw Plugin
 *
 * Bridges OpenClaw with the simple-rag-arch memory system.
 * Provides persistent memory search, note storage, session tracking,
 * and workflow checkpoints via the local SQLite RAG database.
 *
 * Installation:
 *   Copy this directory to ~/.openclaw/extensions/rag-memory/
 *   Enable: openclaw plugins enable rag-memory
 *   Verify: openclaw plugins inspect rag-memory
 *
 * Configuration:
 *   openclaw config set plugins.rag-memory.agentId "linux-admin"
 *   openclaw config set plugins.rag-memory.autoSaveSessions true
 *   openclaw config set plugins.rag-memory.injectContext true
 */

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import * as path from "node:path";

// ── Helpers ───────────────────────────────────────────────────────

function textResult(text, details) {
  return {
    content: [{ type: "text", text }],
    details: details || {},
  };
}

// ── RAG Bridge ───────────────────────────────────────────────────────

function getRagDir() {
  const home = process.env.HOME || "/home/hendra";
  return path.join(home, "simple-rag-arch");
}

function getDbPath() {
  return path.join(getRagDir(), "memory", "memory.db");
}

function getVenvePython() {
  return path.join(getRagDir(), ".venv", "bin", "python3");
}

function dbReady() {
  return existsSync(getDbPath());
}

/**
 * Run a Python one-liner against the RAG DB scripts.
 * Returns stdout trimmed, or null on error.
 */
function runPy(oneLiner) {
  if (!dbReady()) return null;
  const pyCode = `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(getRagDir(), "scripts"))}); ${oneLiner}`;
  try {
    return execSync(`${getVenvePython()} -c ${JSON.stringify(pyCode)}`, {
      encoding: "utf-8",
      timeout: 10_000,
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
  } catch (e) {
    console.error(`[rag-memory] Python error: ${e.message}`);
    return null;
  }
}

function searchNotes(query, limit = 5) {
  const raw = runPy(
    `from db import search_notes; notes = search_notes(${JSON.stringify(query)}, ${limit}); print(json.dumps([dict(n) for n in notes]))`
  );
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function searchSessions(query, limit = 5) {
  const raw = runPy(
    `from db import search_sessions; ss = search_sessions(${JSON.stringify(query)}, ${limit}); print(json.dumps([dict(s) for s in ss]))`
  );
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function addNote(agentId, title, content, tags = [], importance = 1) {
  const raw = runPy(
    `from db import add_note; n = add_note(${JSON.stringify(agentId)}, ${JSON.stringify(title)}, ${JSON.stringify(content)}, ${JSON.stringify(tags)}, ${importance}); print(json.dumps(dict(n)))`
  );
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function startSession(agentId) {
  const raw = runPy(
    `from db import start_session; sid = start_session(${JSON.stringify(agentId)}); print(sid)`
  );
  if (!raw) return null;
  const n = parseInt(raw, 10);
  return Number.isNaN(n) ? null : n;
}

function endSession(sessionId, summary, whatWorked = [], whatFailed = [], tokenCount = 0) {
  const raw = runPy(
    `from db import end_session; end_session(${sessionId}, ${JSON.stringify(summary)}, ${JSON.stringify(whatWorked)}, ${JSON.stringify(whatFailed)}, token_count=${tokenCount}); print("ok")`
  );
  return raw === "ok";
}

function getPendingTasks(agentId) {
  const raw = runPy(
    `from db import get_pending_tasks; tasks = get_pending_tasks(${JSON.stringify(agentId)}); print(json.dumps([dict(t) for t in tasks]))`
  );
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function getAgent(agentId) {
  const raw = runPy(
    `from db import get_agent; a = get_agent(${JSON.stringify(agentId)}); print(json.dumps(dict(a)) if a else "null")`
  );
  if (!raw || raw === "null") return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function listAgents() {
  const raw = runPy(
    `from db import list_agents; agents = list_agents(); print(json.dumps([dict(a) for a in agents]))`
  );
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function autoRegisterAgents() {
  const raw = runPy(
    `from db import auto_register_agents; new_agents = auto_register_agents(); print(len(new_agents))`
  );
  if (!raw) return 0;
  const n = parseInt(raw, 10);
  return Number.isNaN(n) ? 0 : n;
}

function saveCheckpoint(sessionId, taskId, step, status = "running") {
  const raw = runPy(
    `from db import save_checkpoint; save_checkpoint(${sessionId ?? "None"}, ${JSON.stringify(taskId)}, ${step}, ${JSON.stringify(status)}); print("ok")`
  );
  return raw === "ok";
}

function buildRuntimePrompt(agentId, maxTokens = 2000) {
  return runPy(
    `from db import build_runtime_prompt; prompt = build_runtime_prompt(${JSON.stringify(agentId)}, ${maxTokens}); print(prompt)`
  );
}

// ── N+1 Next Step Tracking ────────────────────────────────────────────

function addNextStep(description, priority = 0, sessionId = null, taskId = null) {
  const taskIdArg = taskId !== null ? `, task_id=${JSON.stringify(taskId)}` : "";
  const raw = runPy(
    `from db import add_next_step; ns = add_next_step(${sessionId ?? "None"}, ${JSON.stringify(description)}, ${priority}${taskIdArg}); print(json.dumps(dict(ns)))`
  );
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

function getPendingNextSteps(agentId, limit = 10) {
  const raw = runPy(
    `from db import get_pending_next_steps; steps = get_pending_next_steps(${JSON.stringify(agentId)}, ${limit}); print(json.dumps([dict(s) for s in steps]))`
  );
  if (!raw) return [];
  try { return JSON.parse(raw); } catch { return []; }
}

function completeNextStep(nextStepId) {
  const raw = runPy(
    `from db import complete_next_step; complete_next_step(${nextStepId}); print("ok")`
  );
  return raw === "ok";
}

// ── Retrieval Router Bridge ────────────────────────────────────────────

const MIDDLEWARE_DIR = path.join(getRagDir(), "middleware");

function retrieve(query, agentId, limit = 5) {
  const raw = runPy(
    `sys.path.insert(0, ${JSON.stringify(MIDDLEWARE_DIR)}); ` +
    `from retrieval_router import retrieve; ` +
    `result = retrieve(${JSON.stringify(query)}, ${JSON.stringify(agentId)}, ${limit}); ` +
    `print(json.dumps(result, default=str))`
  );
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

function formatRetrievalContext(routerResult) {
  const raw = runPy(
    `sys.path.insert(0, ${JSON.stringify(MIDDLEWARE_DIR)}); ` +
    `from retrieval_router import format_retrieval_context; ` +
    `print(format_retrieval_context(${JSON.stringify(routerResult)}))`
  );
  return raw;
}

// ── Tool definitions ─────────────────────────────────────────────────

function createRagSearchTool(api) {
  return {
    name: "rag_search",
    label: "RAG Search",
    description:
      "Search the RAG memory system using the Retrieval Router with confidence scoring. " +
      "Checks checkpoints, recent sessions, and FTS5 in priority order. " +
      "Results include confidence level (HIGH/MEDIUM/LOW). " +
      "When confidence is LOW, consider external search fallback.",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Search query (full-text search across checkpoints, sessions, and notes)",
        },
        limit: {
          type: "number",
          description: "Max results (default: 5)",
          default: 5,
        },
      },
      required: ["query"],
    },
    execute: async (_toolCallId, rawParams) => {
      if (!dbReady()) {
        return textResult("⚠ RAG database not available. Check ~/simple-rag-arch/memory/memory.db");
      }

      const query = String(rawParams.query || "");
      const limit = parseInt(rawParams.limit, 10) || 5;
      const agentId = (api.config && api.config.agentId) || "linux-admin";

      const result = retrieve(query, agentId, limit);

      if (!result) {
        return textResult(`❌ Retrieval Router error for "${query}".`);
      }

      // Use the router's formatted context if available
      const formatted = formatRetrievalContext(result);

      if (formatted) {
        return textResult(formatted);
      }

      // Fallback: manual formatting
      const parts = [];
      parts.push(`── Memory Retrieval (${(result.confidence_level || "?").toUpperCase()} confidence) ──`);

      if (result.needs_external_fallback) {
        parts.push("⚠ Low confidence — consider external search fallback");
      }

      if (result.results && result.results.length > 0) {
        for (const r of result.results) {
          const src = (r.source || "?").toUpperCase();
          const conf = r.confidence || 0;
          parts.push(`\n- [${src}] confidence=${conf}: ${(r.content || "").slice(0, 200)}`);
        }
      } else {
        parts.push(`\nNo results found for "${query}".`);
      }

      return textResult(parts.join("\n"));
    },
  };
}

function createRagNoteTool(api) {
  return {
    name: "rag_note",
    label: "RAG Note",
    description:
      "Save a knowledge note to the RAG memory system. " +
      "Use this when you learn something important, make a decision, " +
      "or discover a pattern worth remembering across sessions.",
    parameters: {
      type: "object",
      properties: {
        title: {
          type: "string",
          description: "Short title for the note",
        },
        content: {
          type: "string",
          description: "Detailed note content — what you learned or decided",
        },
        tags: {
          type: "string",
          description: "Comma-separated tags (e.g. lesson, config, project, infra)",
        },
        importance: {
          type: "number",
          description: "Importance 1-5 (1=normal, 5=critical)",
          default: 1,
        },
      },
      required: ["title", "content"],
    },
    execute: async (_toolCallId, rawParams) => {
      if (!dbReady()) {
        return textResult("⚠ RAG database not available.");
      }

      const agentId = (api.config && api.config.agentId) || "linux-admin";
      const title = String(rawParams.title || "");
      const content = String(rawParams.content || "");
      const tags = rawParams.tags
        ? String(rawParams.tags).split(",").map((t) => t.trim()).filter(Boolean)
        : [];
      const importance = parseInt(rawParams.importance, 10) || 1;

      const note = addNote(agentId, title, content, tags, importance);
      if (note) {
        return textResult(`✅ Saved note #${note.id}: "${title}" [${tags.join(", ") || "untagged"}]`);
      }

      return textResult("❌ Failed to save note.");
    },
  };
}

function createRagStatusTool(api) {
  return {
    name: "rag_status",
    label: "RAG Status",
    description:
      "Show the current RAG memory status — active session, pending tasks, " +
      "pending next steps (N+1), and registered agents. Check this before starting new work.",
    parameters: {
      type: "object",
      properties: {},
    },
    execute: async () => {
      if (!dbReady()) {
        return textResult("⚠ RAG database not available.");
      }

      const agentId = (api.config && api.config.agentId) || "linux-admin";
      const lines = [];
      const agent = getAgent(agentId);
      if (agent) {
        lines.push(`**Agent**: ${agent.name} (${agent.id})`);
      } else {
        lines.push(`**Agent**: ${agentId} (not registered in RAG)`);
      }

      const tasks = getPendingTasks(agentId);
      if (tasks.length > 0) {
        lines.push(`\n**Pending tasks**: ${tasks.length}`);
        for (const t of tasks) {
          lines.push(`  - ${t.task_id} step ${t.step} → ${t.status} (retries: ${t.retry_count})`);
        }
      } else {
        lines.push("\n**Pending tasks**: none ✅");
      }

      // N+1 next steps
      const nextSteps = getPendingNextSteps(agentId);
      if (nextSteps.length > 0) {
        lines.push(`\n**N+1 — Next steps** (${nextSteps.length}):`);
        for (const ns of nextSteps) {
          const prio = ns.priority > 0 ? ` [prio:${ns.priority}]` : "";
          lines.push(`  ${ns.id}. ${ns.description}${prio}`);
        }
      } else {
        lines.push("\n**N+1 — Next steps**: none ✅");
      }

      const allAgents = listAgents();
      if (allAgents.length > 0) {
        lines.push(`\n**Registered agents** (${allAgents.length}):`);
        for (const a of allAgents) {
          lines.push(`  - ${a.name} (${a.id})`);
        }
      }

      return textResult(lines.join("\n"));
    },
  };
}

function createRagNextStepTool(api) {
  return {
    name: "rag_next_step",
    label: "➡️ RAG Next Step (N+1)",
    description:
      "Record what the NEXT step should be after the current work. " +
      "Creates a N+1 todo that will be shown in future sessions for resumable workflows. " +
      "SYNC: Provide task_id to link to a checkpoint task — auto-completes when checkpoint succeeds.",
    parameters: {
      type: "object",
      properties: {
        description: {
          type: "string",
          description: "What should happen next? Describe the next action clearly.",
        },
        priority: {
          type: "number",
          description: "Priority 0-5 (0=normal, 5=urgent)",
          default: 0,
        },
        taskId: {
          type: "string",
          description: "Link to a checkpoint task_id (e.g. 'build-api', 'fix-auth'). " +
            "Auto-completes when the checkpoint task finishes. Prevents duplicates.",
        },
      },
      required: ["description"],
    },
    execute: async (_toolCallId, rawParams) => {
      if (!dbReady()) {
        return textResult("⚠ RAG database not available.");
      }
      const description = String(rawParams.description || "");
      const priority = parseInt(rawParams.priority, 10) || 0;
      const taskId = rawParams.taskId ? String(rawParams.taskId) : null;
      const ns = addNextStep(description, priority, null, taskId);
      if (ns) {
        const linked = taskId ? ` (linked to task: ${taskId})` : "";
        return textResult(`➡️ N+1 recorded: "${description}" (priority: ${priority})${linked}`);
      }
      return textResult("❌ Failed to save next step");
    },
  };
}

function createRagCheckpointTool(api) {
  return {
    name: "rag_checkpoint",
    label: "RAG Checkpoint",
    description:
      "Save a workflow checkpoint that can be resumed later if interrupted. " +
      "Use this for multi-step tasks to track progress.\n\n" +
      "AUTO-SYNC WITH N+1: When status='success', any N+1 linked to the same " +
      "task_id auto-completes. No need to call rag_next_step separately.",
    parameters: {
      type: "object",
      properties: {
        taskId: {
          type: "string",
          description: "Task identifier (e.g. scrape-data, build-api, fix-auth)",
        },
        step: {
          type: "number",
          description: "Current step number in the task",
        },
        status: {
          type: "string",
          description: "Status: running, success, failed, or pending",
          enum: ["running", "success", "failed", "pending"],
          default: "running",
        },
        description: {
          type: "string",
          description: "What happened at this checkpoint",
        },
      },
      required: ["taskId", "step"],
    },
    execute: async (_toolCallId, rawParams) => {
      if (!dbReady()) {
        return textResult("⚠ RAG database not available.");
      }

      const taskId = String(rawParams.taskId || "");
      const step = parseInt(rawParams.step, 10) || 1;
      const status = String(rawParams.status || "running");
      const sessionId = null; // OpenClaw session mapping TBD

      const ok = saveCheckpoint(sessionId, taskId, step, status);
      if (!ok) {
        return textResult(`❌ Failed to save checkpoint for ${taskId} step ${step}.`);
      }

      const statusIcons = {
        running: "▶️",
        pending: "⏳",
        success: "✅",
        failed: "❌",
      };
      const desc = rawParams.description ? ` — ${String(rawParams.description)}` : "";

      return textResult(
        `${statusIcons[status] || "📌"} Checkpoint: ${taskId} step ${step} → ${status}${desc}`
      );
    },
  };
}

// ── Context injection ────────────────────────────────────────────────

/**
 * Build a RAG context string for injection into the agent prompt.
 */
function buildRagContextString(agentId) {
  if (!dbReady()) return null;

  const parts = [];
  const agent = getAgent(agentId);
  if (agent) {
    parts.push(`RAG Agent: ${agent.name} (${agent.id})`);
  }

  // Recent notes
  const notes = searchNotes("*", 3);
  if (notes.length > 0) {
    parts.push("\nRecent RAG notes:");
    for (const n of notes) {
      const tags = n.tags ? ` [${n.tags}]` : "";
      parts.push(`  - ${n.title}${tags}`);
    }
  }

  // Pending tasks
  const tasks = getPendingTasks(agentId);
  if (tasks.length > 0) {
    parts.push(`\nPending RAG tasks: ${tasks.length}`);
    for (const t of tasks) {
      parts.push(`  - ${t.task_id} step ${t.step} → ${t.status}`);
    }
  }

  // N+1 next steps
  const nextSteps = getPendingNextSteps(agentId, 5);
  if (nextSteps.length > 0) {
    parts.push(`\nN+1 next steps: ${nextSteps.length}`);
    for (const ns of nextSteps) {
      parts.push(`  - ${ns.description}`);
    }
  }

  return parts.length > 0 ? parts.join("\n") : null;
}

// ── Plugin Entry ─────────────────────────────────────────────────────

export default definePluginEntry({
  id: "rag-memory",
  name: "RAG Memory",
  description:
    "Local-first memory system bridging simple-rag-arch SQLite database. " +
    "Persistent session summaries, knowledge notes, workflow checkpoints, and cross-session recall.",

  register(api) {
    const agentId = (api.config && api.config.agentId) || "linux-admin";
    const injectContext = api.config?.injectContext !== false;
    const autoSave = api.config?.autoSaveSessions !== false;

    if (dbReady()) {
      api.logger?.info?.("[rag-memory] RAG database found at " + getDbPath());

      // Auto-discover any new agent persona files in agents/ directory
      const newCount = autoRegisterAgents();
      if (newCount > 0) {
        api.logger?.info?.("[rag-memory] " + newCount + " new agent(s) auto-registered from agents/");
      }
    } else {
      api.logger?.warn?.("[rag-memory] RAG database not found at " + getDbPath());
    }

    // ── Register Tools ──────────────────────────────────────────────

    api.registerTool(createRagSearchTool(api));
    api.registerTool(createRagNoteTool(api));
    api.registerTool(createRagStatusTool(api));
    api.registerTool(createRagCheckpointTool(api));
    api.registerTool(createRagNextStepTool(api));

    // ── Add rag_configure tool (switch agent identity) ───────────────

    api.registerTool({
      name: "rag_configure",
      label: "RAG Configure",
      description:
        "Switch the RAG agent identity to any agent with a persona file in agents/. " +
        "Auto-registers new agents on the fly.",
      parameters: {
        type: "object",
        properties: {
          agentId: {
            type: "string",
            description: "Agent ID (e.g. linux-admin, pi-code, ops, coder, research)",
          },
        },
        required: ["agentId"],
      },
      execute: async (_toolCallId, rawParams) => {
        if (!dbReady()) {
          return textResult("⚠ RAG database not available.");
        }
        const newAgentId = String(rawParams.agentId || "");
        if (!newAgentId) {
          return textResult("⚠ Please provide an agentId.");
        }

        // Auto-register if a new persona file exists
        autoRegisterAgents();

        // Update config
        if (api.config) {
          const oldId = api.config.agentId || "?";
          api.config.agentId = newAgentId;
          return textResult(`✅ Switched RAG agent from "${oldId}" to "${newAgentId}"`);
        }
        return textResult(`✅ RAG agent set to "${newAgentId}"`);
      },
    });

    // ── Before prompt build: inject RAG context + track turns ─────

    let currentSessionId = null;
    let turnCount = 0;

    api.on("before_prompt_build", async (_event, ctx) => {
      turnCount++;

      if (!injectContext) return;
      try {
        const resolvedAgentId = agentId;
        const contextStr = buildRagContextString(resolvedAgentId);
        if (contextStr) {
          const prefix =
            "[RAG Memory Context]\n" +
            contextStr +
            "\n\n" +
            "Use rag_search to search memory, rag_note to save knowledge, " +
            "rag_checkpoint for workflow progress, rag_next_step for N+1 tracking, " +
            "and rag_status to check pending tasks.\n";

          return { prependContext: prefix };
        }
      } catch (e) {
        api.logger?.warn?.(
          "[rag-memory] before_prompt_build failed: " + (e.message || String(e))
        );
      }
    });

    // ── Session tracking ────────────────────────────────────────────

    api.on("session_start", async (_event, _ctx) => {
      if (!dbReady() || !autoSave) return;
      currentSessionId = startSession(agentId);
      turnCount = 0;
      if (currentSessionId) {
        api.logger?.info?.("[rag-memory] Started RAG session " + currentSessionId);
      }
    });

    api.on("session_end", async (_event, _ctx) => {
      if (!dbReady() || !autoSave || currentSessionId === null) return;
      endSession(
        currentSessionId,
        `OpenClaw session: ${turnCount} turns`,
        [],
        [],
        turnCount
      );
      api.logger?.info?.("[rag-memory] Ended RAG session " + currentSessionId);
      currentSessionId = null;
      turnCount = 0;
    });
  },
});
