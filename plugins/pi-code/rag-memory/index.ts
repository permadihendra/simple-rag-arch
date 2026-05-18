/**
 * rag-memory — Pi Code RAG Memory Extension
 *
 * Bridges Pi Code agent with the simple-rag-arch memory system.
 * Provides:
 *   - 6 dedicated slash commands (/rag-search, /rag-status, /rag-note, etc.)
 *   - 6 custom tools (rag_search, rag_note, rag_status, rag_checkpoint, rag_end_session, rag_configure)
 *   - Auto-RAG reflex: injects RAG usage rules into system prompt before each turn
 *   - Session auto-tracking with rich summaries
 *   - Workflow checkpoints for resumable tasks
 *
 * Installation:
 *   Copy to ~/.pi/agent/extensions/rag-memory/
 *   Auto-discovered on pi restart.
 *
 * The extension is fully swappable — just rename the directory to disable.
 */

import type {
  ExtensionAPI,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import * as path from "node:path";
import * as fs from "node:fs";
import * as rag from "./rag-bridge";

// ── Types ───────────────────────────────────────────────────────────

interface RAGSessionState {
  agentId: string;
  sessionId: number | null;
  startedAt: string;
  turnCount: number;
  whatWorked: string[];
  whatFailed: string[];
}

// ── Extension Entry ─────────────────────────────────────────────────

export default function ragMemoryExtension(pi: ExtensionAPI) {
  // ── State ───────────────────────────────────────────────────────────

  const CONFIG_PATH = path.join(
    process.env.HOME || "~",
    ".pi",
    "agent",
    "extensions",
    "rag-memory",
    "config.json"
  );

  let config: { agentId: string } = { agentId: "pi-code" };
  let state: RAGSessionState = {
    agentId: "pi-code",
    sessionId: null,
    startedAt: new Date().toISOString(),
    turnCount: 0,
    whatWorked: [],
    whatFailed: [],
  };
  let dbReady = false;

  // Load config
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      config = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
    }
  } catch {
    // use defaults
  }

  // Check DB
  dbReady = rag.dbExists();

  // Persist config
  function saveConfig() {
    try {
      fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
      fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
    } catch {}
  }

  // ── Helpers ─────────────────────────────────────────────────────────

  function getAgentId(): string {
    return config.agentId;
  }

  function setAgentId(id: string) {
    config.agentId = id;
    state.agentId = id;
    saveConfig();
  }

  function startRagSession(agentId: string): number | null {
    if (!dbReady) return null;
    const sid = rag.startSession(agentId);
    if (sid !== null) {
      state.sessionId = sid;
      state.startedAt = new Date().toISOString();
      state.turnCount = 0;
      state.whatWorked = [];
      state.whatFailed = [];
      pi.appendEntry("rag-session", {
        sessionId: sid,
        agentId,
        startedAt: state.startedAt,
      });
    }
    return sid;
  }

  function doEndRagSession(summary: string, worked: string[], failed: string[]) {
    if (!dbReady || state.sessionId === null) return;
    rag.endSession(state.sessionId, summary, worked, failed, state.turnCount);

    // Auto-save what worked/failed as notes for future recall
    for (const w of worked.slice(0, 3)) {
      rag.addNote(getAgentId(), `✅ ${w.slice(0, 60)}`, w, ["session-auto"], 1);
    }
    for (const f of failed.slice(0, 3)) {
      rag.addNote(getAgentId(), `⚠ ${f.slice(0, 60)}`, f, ["session-auto", "blocker"], 3);
    }

    pi.appendEntry("rag-session-end", {
      sessionId: state.sessionId,
      summary,
      endedAt: new Date().toISOString(),
    });

    state.sessionId = null;
    state.turnCount = 0;
    state.whatWorked = [];
    state.whatFailed = [];
  }

  // ── Restore state from persisted entries ────────────────────────────

  function restoreState(ctx: ExtensionContext) {
    const branch = ctx.sessionManager.getBranch();
    for (const entry of branch) {
      if (entry.type !== "custom") continue;
      if (entry.customType === "rag-config" && entry.data?.agentId) {
        config.agentId = entry.data.agentId;
      }
      if (entry.customType === "rag-session" && entry.data?.sessionId) {
        state.sessionId = entry.data.sessionId;
        state.startedAt = entry.data.startedAt;
      }
      if (entry.customType === "rag-session-end") {
        state.sessionId = null;
      }
    }
  }

  // ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ─
  //  EVENTS
  // ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ─

  // ── Session start: restore + notify ───────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    restoreState(ctx);

    if (!dbReady) {
      ctx.ui.notify("⚠ RAG DB not found at ~/simple-rag-arch/memory/memory.db", "warning");
      return;
    }

    const agentId = getAgentId();
    const prompt = rag.buildRuntimePrompt(agentId);
    if (prompt) {
      ctx.ui.notify(`🧠 RAG context loaded for ${agentId}`, "info");
    }

    if (state.sessionId === null) {
      startRagSession(agentId);
    }
  });

  // ── Session shutdown: auto-save ───────────────────────────────────

  pi.on("session_shutdown", async (_event, _ctx) => {
    if (state.sessionId !== null && dbReady) {
      doEndRagSession(
        `Session ${state.sessionId}: ${state.turnCount} turns (interrupted)`,
        state.whatWorked,
        state.whatFailed
      );
    }
  });

  // ── Before each turn: inject RAG rules + context ──────────────────

  pi.on("before_agent_start", async (event, ctx) => {
    state.turnCount++;

    // Always inject RAG usage rules so the LLM knows to use memory first
    const ragRules = `
── RAG Memory Rules — YOU MUST FOLLOW THESE ──
1. When the user asks about PAST WORK, PROJECT HISTORY, something you "should know", or anything referencing previous sessions — you MUST call rag_search FIRST before answering.
2. When the user says "remember this", "save this", "note this", "keep this" — call rag_note immediately to persist it.
3. When working on a multi-step task — call rag_checkpoint after each step so work is resumable.
4. When the user seems done or explicitly ends — call rag_end_session with a good summary and what_worked/what_failed.
5. At the start of any session, check rag_status to see what's pending.
6. rag_search is your long-term memory — USE IT. Don't guess about past work, look it up.
`;

    if (!dbReady) {
      return { systemPrompt: event.systemPrompt + ragRules };
    }

    const agentId = getAgentId();
    const prompt = rag.buildRuntimePrompt(agentId, 2000);
    const contextBlock = prompt
      ? `\n\n── RAG Memory Context ──\n${prompt}`
      : "";

    return {
      systemPrompt: event.systemPrompt + ragRules + contextBlock,
    };
  });

  // ── Agent end: extract learnings ──────────────────────────────────

  pi.on("agent_end", async (event, _ctx) => {
    const messages = event.messages;
    for (const msg of messages) {
      if (msg.role === "tool" && msg.toolResult?.isError) {
        const desc = `${msg.toolName}: ${String(msg.content ?? "").slice(0, 80)}`;
        if (!state.whatFailed.includes(desc)) {
          state.whatFailed.push(desc);
        }
      }
    }
  });

  // ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ─
  //  CUSTOM TOOLS (callable by the LLM)
  // ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ─

  // ── rag_search ────────────────────────────────────────────────────
  pi.registerTool({
    name: "rag_search",
    label: "🔍 RAG Search",
    description:
      "Search the RAG memory system for notes and session summaries. " +
      "Call this BEFORE answering any question about past work, project history, " +
      "lessons learned, or anything the user expects you to remember.",
    promptSnippet: "Search RAG memory — call this BEFORE answering history questions",
    promptGuidelines: [
      "CRITICAL: Before answering questions about past work, project history, or things you should know — ALWAYS call rag_search first.",
      "rag_search is your memory. Use it instead of guessing about what happened before this session.",
    ],
    parameters: Type.Object({
      query: Type.String({
        description: "Search query (FTS5 full-text search over notes and sessions)",
      }),
      limit: Type.Optional(
        Type.Number({ description: "Max results (default: 5)", default: 5 })
      ),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      if (!dbReady) {
        return {
          content: [{ type: "text", text: "⚠ RAG database not available at ~/simple-rag-arch/memory/memory.db" }],
          details: {},
        };
      }

      const notes = rag.searchNotes(params.query, params.limit ?? 5);
      const sessions = rag.searchSessions(params.query, params.limit ?? 5);

      const parts: string[] = [];

      if (notes.length > 0) {
        parts.push("## 📝 Notes");
        for (const n of notes) {
          const tags = n.tags ? `[${n.tags}]` : "";
          parts.push(
            `- **${n.title}** ${tags}\n  ${n.content.slice(0, 200)}${n.content.length > 200 ? "..." : ""}`
          );
        }
      }

      if (sessions.length > 0) {
        parts.push("## 💬 Sessions");
        for (const s of sessions) {
          parts.push(
            `- Session #${s.id} (${s.agent_id}): ${(s.summary || "(no summary)").slice(0, 150)}`
          );
        }
      }

      if (parts.length === 0) {
        return {
          content: [{ type: "text", text: `No RAG results found for "${params.query}".` }],
          details: {},
        };
      }

      return {
        content: [{ type: "text", text: parts.join("\n\n") }],
        details: { noteCount: notes.length, sessionCount: sessions.length },
      };
    },
  });

  // ── rag_note ──────────────────────────────────────────────────────
  pi.registerTool({
    name: "rag_note",
    label: "📝 RAG Note",
    description:
      "Save a knowledge note to the RAG memory system. " +
      "Call this when the user says 'remember this', 'save this', or when you discover " +
      "something important that should persist across sessions.",
    promptSnippet: "Save a note to RAG memory for cross-session persistence",
    promptGuidelines: [
      "When the user says 'remember this', 'save this', 'note this', or 'keep this' — call rag_note immediately.",
      "Save important decisions, configurations, gotchas, and lessons learned as notes.",
    ],
    parameters: Type.Object({
      title: Type.String({
        description: "Short descriptive title for the note",
      }),
      content: Type.String({
        description: "Full note content — what was learned, decided, or discovered",
      }),
      tags: Type.Optional(
        Type.String({
          description: "Comma-separated tags (e.g. lesson, config, project, infra, decision)",
        })
      ),
      importance: Type.Optional(
        Type.Number({
          description: "Importance 1-5 (1=normal, 3=important, 5=critical)",
          default: 1,
        })
      ),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      if (!dbReady) {
        return { content: [{ type: "text", text: "⚠ RAG database not available." }], details: {} };
      }

      const tags = params.tags
        ? params.tags.split(",").map((t) => t.trim()).filter(Boolean)
        : [];
      const note = rag.addNote(
        getAgentId(),
        params.title,
        params.content,
        tags,
        params.importance ?? 1
      );

      if (note) {
        state.whatWorked.push(`Note: ${params.title}`);
        return {
          content: [
            {
              type: "text",
              text: `✅ Saved note #${note.id}: "${params.title}" [${tags.join(", ") || "untagged"}]`,
            },
          ],
          details: { noteId: note.id },
        };
      }

      return { content: [{ type: "text", text: "❌ Failed to save note" }], details: {}, isError: true };
    },
  });

  // ── rag_status ────────────────────────────────────────────────────
  pi.registerTool({
    name: "rag_status",
    label: "📊 RAG Status",
    description:
      "Show the current RAG memory status — active session, pending tasks, " +
      "registered agents, and DB health. Call this at the start of work to check context.",
    promptSnippet: "Check RAG memory status and pending tasks",
    promptGuidelines: [
      "Call rag_status at the start of each session to see what work is pending and what was left unfinished.",
    ],
    parameters: Type.Object({}),
    async execute(_toolCallId, _params, _signal, _onUpdate, _ctx) {
      const lines: string[] = [];
      const agentId = getAgentId();

      const agent = rag.getAgent(agentId);
      lines.push(agent
        ? `**Agent**: ${agent.name} (${agent.id})`
        : `**Agent**: ${agentId} (not registered in RAG)`);

      lines.push(`**Active RAG session**: ${state.sessionId ?? "none"}`);
      lines.push(`**Turns this session**: ${state.turnCount}`);
      lines.push(`**DB ready**: ${dbReady ? "✅" : "❌"}`);

      if (dbReady && agentId) {
        const tasks = rag.getPendingTasks(agentId);
        if (tasks.length > 0) {
          lines.push(`\n**Pending tasks** (${tasks.length}):`);
          for (const t of tasks) {
            lines.push(`  - ${t.task_id} step ${t.step} → ${t.status} (retries: ${t.retry_count})`);
          }
        } else {
          lines.push("\n**Pending tasks**: none ✅");
        }

        const allAgents = rag.listAgents();
        if (allAgents.length > 0) {
          lines.push(`\n**Registered agents** (${allAgents.length}):`);
          for (const a of allAgents) {
            lines.push(`  - ${a.name} (${a.id})`);
          }
        }
      }

      return {
        content: [{ type: "text", text: lines.join("\n") }],
        details: { sessionId: state.sessionId, turnCount: state.turnCount, dbReady },
      };
    },
  });

  // ── rag_checkpoint ────────────────────────────────────────────────
  pi.registerTool({
    name: "rag_checkpoint",
    label: "📍 RAG Checkpoint",
    description:
      "Save a workflow checkpoint that can be resumed if interrupted. " +
      "Use for multi-step tasks — call after each step so progress is never lost.",
    promptSnippet: "Save a workflow checkpoint for resumable tasks",
    promptGuidelines: [
      "For multi-step tasks, call rag_checkpoint after each step to track progress.",
      "If a task fails, call rag_checkpoint with status='failed' and a description of what went wrong.",
    ],
    parameters: Type.Object({
      taskId: Type.String({
        description: "Task identifier (e.g. scrape-data, build-api, fix-auth)",
      }),
      step: Type.Number({
        description: "Current step number in the task",
      }),
      status: Type.Optional(
        Type.String({
          description: "Status: running, success, failed, or pending",
          default: "running",
        })
      ),
      description: Type.Optional(
        Type.String({
          description: "What happened at this checkpoint",
        })
      ),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      if (!dbReady) {
        return { content: [{ type: "text", text: "⚠ RAG database not available." }], details: {} };
      }

      const ok = rag.saveCheckpoint(
        state.sessionId,
        params.taskId,
        params.step,
        params.status ?? "running"
      );

      if (!ok) {
        return {
          content: [{ type: "text", text: `❌ Failed to save checkpoint for ${params.taskId} step ${params.step}` }],
          details: {},
          isError: true,
        };
      }

      const icons: Record<string, string> = {
        running: "▶️", pending: "⏳", success: "✅", failed: "❌",
      };
      const desc = params.description ? ` — ${params.description}` : "";

      return {
        content: [{ type: "text", text: `${icons[params.status ?? "running"] || "📌"} Checkpoint: ${params.taskId} step ${params.step} → ${params.status}${desc}` }],
        details: { taskId: params.taskId, step: params.step, status: params.status },
      };
    },
  });

  // ── rag_end_session ───────────────────────────────────────────────
  pi.registerTool({
    name: "rag_end_session",
    label: "🏁 RAG End Session",
    description:
      "End the current RAG session with a summary. Call this when work is complete. " +
      "What you provide here will be remembered in future sessions.",
    promptSnippet: "End RAG session with summary — saves what worked/failed as notes",
    promptGuidelines: [
      "When the user seems done, or explicitly says 'end session' — call rag_end_session with a meaningful summary.",
      "Include what_worked and what_failed — these get auto-saved as notes for future recall.",
    ],
    parameters: Type.Object({
      summary: Type.String({
        description: "Summary of what was accomplished this session",
      }),
      whatWorked: Type.Optional(
        Type.String({
          description: "Comma-separated: what worked well, what was completed",
        })
      ),
      whatFailed: Type.Optional(
        Type.String({
          description: "Comma-separated: what failed, what's blocked, what needs follow-up",
        })
      ),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      if (!dbReady || state.sessionId === null) {
        return { content: [{ type: "text", text: "⚠ No active RAG session to end." }], details: {} };
      }

      const worked = params.whatWorked
        ? params.whatWorked.split(",").map((s) => s.trim()).filter(Boolean)
        : state.whatWorked;
      const failed = params.whatFailed
        ? params.whatFailed.split(",").map((s) => s.trim()).filter(Boolean)
        : state.whatFailed;

      doEndRagSession(params.summary, worked, failed);

      return {
        content: [{
          type: "text",
          text: `✅ Session ${state.sessionId} ended\nSummary: ${params.summary}\nWorked: ${worked.length} items\nFailed: ${failed.length} items`,
        }],
        details: {},
      };
    },
  });

  // ── rag_configure ─────────────────────────────────────────────────
  pi.registerTool({
    name: "rag_configure",
    label: "⚙️ RAG Configure",
    description: "Switch the RAG agent identity (pi-code, linux-admin, main, ops, coder, research).",
    promptSnippet: "Switch RAG agent identity",
    parameters: Type.Object({
      agentId: Type.String({
        description: "Agent ID: pi-code, linux-admin, main, ops, coder, research",
      }),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const oldId = getAgentId();
      setAgentId(params.agentId);

      if (state.sessionId !== null && dbReady) {
        rag.endSession(state.sessionId, `Switched from ${oldId} to ${params.agentId}`, [], [], 0);
        state.sessionId = null;
      }

      if (dbReady) startRagSession(params.agentId);

      return {
        content: [{ type: "text", text: `✅ Switched RAG agent from "${oldId}" to "${params.agentId}"` }],
        details: { previousAgent: oldId, currentAgent: params.agentId },
      };
    },
  });

  // ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ─
  //  SLASH COMMANDS (typed directly by user)
  // ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ─

  pi.registerCommand("rag-search", {
    description: "Search RAG memory: /rag-search <query>",
    handler: async (args, ctx) => {
      const query = args.trim();
      if (!query) {
        ctx.ui.notify("Usage: /rag-search <query>", "warning");
        return;
      }
      const notes = rag.searchNotes(query);
      const sessions = rag.searchSessions(query);
      let msg = `🔍 "${query}" → ${notes.length} notes, ${sessions.length} sessions`;
      if (notes.length > 0) {
        msg += `\n📝 ${notes.slice(0, 3).map((n) => n.title).join(", ")}`;
      }
      ctx.ui.notify(msg, "info");
    },
  });

  pi.registerCommand("rag-status", {
    description: "Show RAG memory status",
    handler: async (_args, ctx) => {
      const agentId = getAgentId();
      const tasks = rag.getPendingTasks(agentId);
      const agent = rag.getAgent(agentId);
      const lines = [
        `🧠 RAG: ${agent ? agent.name : agentId}`,
        `   Session: ${state.sessionId ?? "none"}`,
        `   Turns: ${state.turnCount}`,
        `   DB: ${dbReady ? "✅" : "❌"}`,
      ];
      if (tasks.length > 0) {
        lines.push(`   Pending tasks (${tasks.length}):`);
        for (const t of tasks) {
          lines.push(`     - ${t.task_id} step ${t.step} → ${t.status}`);
        }
      }
      ctx.ui.notify(lines.join("\n"), "info");
    },
  });

  pi.registerCommand("rag-note", {
    description: "Save a RAG note: /rag-note <title> | <content> | <tags>",
    handler: async (args, ctx) => {
      if (!args.includes("|")) {
        ctx.ui.notify("Usage: /rag-note Title | Content here | tag1,tag2", "warning");
        return;
      }
      const parts = args.split("|").map((s) => s.trim());
      const title = parts[0] || "Untitled";
      const content = parts[1] || "";
      const tags = parts[2] ? parts[2].split(",").map((t) => t.trim()) : [];

      const note = rag.addNote(getAgentId(), title, content, tags);
      if (note) {
        ctx.ui.notify(`✅ Note #${note.id}: "${title}" saved`, "info");
      } else {
        ctx.ui.notify("❌ Failed to save note", "error");
      }
    },
  });

  pi.registerCommand("rag-end", {
    description: "End the current RAG session with a summary: /rag-end <summary>",
    handler: async (args, ctx) => {
      if (state.sessionId === null) {
        ctx.ui.notify("No active RAG session", "warning");
        return;
      }
      const summary = args.trim() || `Session ${state.sessionId}`;
      doEndRagSession(summary, state.whatWorked, state.whatFailed);
      ctx.ui.notify(`✅ Session ${state.sessionId} ended`, "info");
    },
  });

  pi.registerCommand("rag-checkpoint", {
    description: "Save a checkpoint: /rag-checkpoint <taskId> <step> [status]",
    handler: async (args, ctx) => {
      const parts = args.trim().split(/\s+/);
      const taskId = parts[0];
      const step = parseInt(parts[1], 10);
      const status = parts[2] || "running";
      if (!taskId || isNaN(step)) {
        ctx.ui.notify("Usage: /rag-checkpoint <taskId> <step> [status]", "warning");
        return;
      }
      const ok = rag.saveCheckpoint(state.sessionId, taskId, step, status);
      ctx.ui.notify(ok ? `📍 ${taskId} step ${step} → ${status}` : "❌ Failed", ok ? "info" : "error");
    },
  });

  pi.registerCommand("rag-config", {
    description: "Configure RAG agent: /rag-config <agentId>",
    handler: async (args, ctx) => {
      const id = args.trim();
      if (!id) {
        ctx.ui.notify(`Current RAG agent: ${getAgentId()}`, "info");
        return;
      }
      setAgentId(id);
      ctx.ui.notify(`✅ RAG agent set to ${id}`, "info");
    },
  });
}
