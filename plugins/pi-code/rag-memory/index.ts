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
  /** Track user messages that mention saving/remembering, so we can auto-extract notes */
  pendingMemoryHints: Array<{ text: string; timestamp: string }>;
  /** Track if last turn had a rag_note call to avoid duplicates */
  lastTurnHadNoteCall: boolean;
  /** Current session note/checkpoint count for richer context */
  sessionNoteCount: number;
  sessionCheckpointCount: number;
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
    pendingMemoryHints: [],
    lastTurnHadNoteCall: false,
    sessionNoteCount: 0,
    sessionCheckpointCount: 0,
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
      state.pendingMemoryHints = [];
      state.lastTurnHadNoteCall = false;
      state.sessionNoteCount = 0;
      state.sessionCheckpointCount = 0;
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
    state.pendingMemoryHints = [];
    state.lastTurnHadNoteCall = false;
    state.sessionNoteCount = 0;
    state.sessionCheckpointCount = 0;
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
      // Build a richer summary from tracked activity
      const activity = [];
      if (state.sessionNoteCount > 0) activity.push(`${state.sessionNoteCount} notes saved`);
      if (state.sessionCheckpointCount > 0) activity.push(`${state.sessionCheckpointCount} checkpoints`);
      if (state.pendingMemoryHints.length > 0) activity.push(`${state.pendingMemoryHints.length} pending memory hints`);
      const activityStr = activity.length > 0 ? ` (${activity.join(", ")})` : "";

      doEndRagSession(
        `Session ${state.sessionId}: ${state.turnCount} turns${activityStr} — interrupted`,
        state.whatWorked,
        state.whatFailed
      );
    }
  });

  // ── Helpers ─────────────────────────────────────────────────────────

  /** Check if a prompt looks like a heartbeat (short, periodic check-in) */
  function isHeartbeat(prompt: string): boolean {
    const lower = prompt.trim().toLowerCase();
    // Heartbeat indicators: very short, contains keywords, or is periodic-status-ish
    const heartbeatKeywords = ["heartbeat", "heart beat", "check in", "status check", "ping"];
    if (heartbeatKeywords.some(k => lower.includes(k))) return true;
    // Very short prompts (<=15 chars) that aren't commands are likely heartbeats
    if (lower.length <= 15 && !lower.startsWith("/")) return true;
    return false;
  }

  // ── Before each turn: inject RAG rules + context ──────────────────

  pi.on("before_agent_start", async (event, ctx) => {
    state.turnCount++;

    const agentId = getAgentId();
    const isHb = isHeartbeat(event.prompt);

    // Always inject RAG usage rules so the LLM knows to use memory first
    const ragRules = isHb
      ? `
── RAG Memory Rules (HEARTBEAT) — YOU MUST FOLLOW THESE ──
1. During heartbeat/quiet periods: call rag_status to check pending N+1 steps.
2. If there are pending N+1 tasks, work on them proactively.
3. Check rag_search for recent memory that might need attention.
4. If something worth remembering happened, call rag_note.
5. Call rag_checkpoint for any progress made.
6. When finished with all N+1 items, reply HEARTBEAT_OK to stay quiet.
`
      : `
── RAG Memory Rules — YOU MUST FOLLOW THESE ──
1. When asked about PAST WORK, PROJECT HISTORY, or things you "should know" — call rag_search FIRST before answering.
2. When user says "remember this", "save this", "note this" — call rag_note immediately.
3. Multi-step tasks — call rag_checkpoint after each step, then rag_next_step to say what N+1 is.
4. When work is done — call rag_end_session with a summary + what_worked/what_failed.
5. Start of session — check rag_status to see pending tasks and N+1 next steps.
6. N+1 is critical: after finishing any step, record what should happen next so work is resumable.
7. rag_search is your memory — USE IT. Don't guess.
`;

    if (!dbReady) {
      return { systemPrompt: event.systemPrompt + ragRules };
    }

    const prompt = rag.buildRuntimePrompt(agentId, 3000);

    // Build current-session activity snippet
    const sessionActivity: string[] = [];
    if (state.sessionNoteCount > 0) {
      sessionActivity.push(`📝 ${state.sessionNoteCount} note(s) saved this session`);
    }
    if (state.sessionCheckpointCount > 0) {
      sessionActivity.push(`📍 ${state.sessionCheckpointCount} checkpoint(s) created this session`);
    }

    // Flush pending memory hints — user wanted to save something
    if (state.pendingMemoryHints.length > 0) {
      for (const hint of state.pendingMemoryHints) {
        sessionActivity.push(`⏳ User mentioned something to remember: "${hint.text.slice(0, 120)}..." — consider calling rag_note if you haven't already`);
      }
      state.pendingMemoryHints = [];
    }

    // If heartbeat, also fetch and inject pending N+1 steps prominently
    if (isHb && dbReady) {
      const nextSteps = rag.getPendingNextSteps(agentId, 5);
      if (nextSteps.length > 0) {
        sessionActivity.push(`\n📋 Pending N+1 steps (check these during heartbeat):`);
        for (const ns of nextSteps) {
          const prio = ns.priority > 0 ? ` [prio:${ns.priority}]` : "";
          sessionActivity.push(`   ${ns.id}. ${ns.description}${prio}`);
        }
        sessionActivity.push(`\n💡 Pro tip: Work on the highest-priority N+1 item. Call rag_next_step after completing each one.`);
      } else {
        sessionActivity.push(`\n✅ No pending N+1 steps. Reply HEARTBEAT_OK.`);
      }
    }

    const activityBlock = sessionActivity.length > 0
      ? `\n\n── This Session Activity ──\n${sessionActivity.join("\n")}`
      : "";

    const contextBlock = prompt
      ? `\n\n── RAG Memory Context ──\n${prompt}${activityBlock}`
      : activityBlock;

    return {
      systemPrompt: event.systemPrompt + ragRules + contextBlock,
    };
  });

  // ── Agent end: extract learnings + auto-note from user hints ────

  pi.on("agent_end", async (event, _ctx) => {
    const messages = event.messages;
    let hadNoteCall = false;
    let hadCheckpointCall = false;

    for (const msg of messages) {
      if (msg.role === "tool") {
        // Track tool calls to know what the LLM already handled
        if (msg.toolName === "rag_note") hadNoteCall = true;
        if (msg.toolName === "rag_checkpoint") hadCheckpointCall = true;

        // Track errors as whatFailed
        if (msg.toolResult?.isError) {
          const desc = `${msg.toolName}: ${String(msg.content ?? "").slice(0, 80)}`;
          if (!state.whatFailed.includes(desc)) {
            state.whatFailed.push(desc);
          }
        }

        // Track successes as whatWorked
        if (msg.toolResult && !msg.toolResult.isError && msg.toolName !== "rag_search" && msg.toolName !== "rag_status") {
          const desc = `${msg.toolName}: ${String(msg.content ?? "").slice(0, 80)}`;
          if (!state.whatWorked.includes(desc) && !desc.includes("No RAG results")) {
            state.whatWorked.push(desc);
          }
        }
      }

      // Detect user messages asking to remember/save things (auto-note hints)
      if (msg.role === "user" && typeof msg.content === "string") {
        const lower = msg.content.toLowerCase();
        const saveTriggers = ["remember this", "save this", "note this", "keep this", "don't forget"];
        if (saveTriggers.some(t => lower.includes(t))) {
          state.pendingMemoryHints.push({
            text: msg.content.slice(0, 200),
            timestamp: new Date().toISOString(),
          });
        }
      }
    }

    state.lastTurnHadNoteCall = hadNoteCall;

    // If the LLM made a note call, bump our session counter
    if (hadNoteCall) state.sessionNoteCount++;
    if (hadCheckpointCall) state.sessionCheckpointCount++;
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
      "pending next steps (N+1), registered agents, and DB health. " +
      "Call this at the start of work to check what needs to be done next.",
    promptSnippet: "Check RAG memory status, pending tasks, and next steps (N+1)",
    promptGuidelines: [
      "Call rag_status at the start of each session to see what work is pending and what the next step (N+1) should be.",
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
        // Pending checkpoints
        const tasks = rag.getPendingTasks(agentId);
        if (tasks.length > 0) {
          lines.push(`\n**Pending tasks** (${tasks.length}):`);
          for (const t of tasks) {
            lines.push(`  - ${t.task_id} step ${t.step} → ${t.status} (retries: ${t.retry_count})`);
          }
        } else {
          lines.push("\n**Pending tasks**: none ✅");
        }

        // N+1: Pending next steps
        const nextSteps = rag.getPendingNextSteps(agentId);
        if (nextSteps.length > 0) {
          lines.push(`\n**N+1 — Next steps** (${nextSteps.length}):`);
          for (const ns of nextSteps) {
            const prio = ns.priority > 0 ? ` [prio:${ns.priority}]` : "";
            lines.push(`  ${ns.id}. ${ns.description}${prio}`);
          }
        } else {
          lines.push("\n**N+1 — Next steps**: none ✅");
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
      "End the current RAG session with a detailed summary. Call this when work is complete. " +
      "Before calling this, review the conversation and generate a structured summary " +
      "with what_worked and what_failed. What you provide here will be remembered in future sessions.",
    promptSnippet: "End RAG session with summary — review conversation first, then save what worked/failed as notes",
    promptGuidelines: [
      "When the user seems done, or explicitly says 'end session' — FIRST review the full conversation, THEN call rag_end_session with a meaningful, comprehensive summary.",
      "Include what_worked and what_failed — these get auto-saved as notes for future recall. Be specific, not generic.",
      "A good summary answers: What did we achieve? What decisions were made? What files were touched? What's the state of things?",
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

  // ── rag_next_step — N+1 tracking ────────────────────────────────
  pi.registerTool({
    name: "rag_next_step",
    label: "➡️ RAG Next Step (N+1)",
    description:
      "Record what the NEXT step should be after the current work. " +
      "This creates a 'N+1' todo that will be shown in future sessions. " +
      "Use this when finishing a step — what should happen next?",
    promptSnippet: "Record the next step (N+1) for resumable workflows",
    promptGuidelines: [
      "When finishing a task step, call rag_next_step to record what comes next (N+1).",
      "This ensures work is resumable even if the session is interrupted.",
    ],
    parameters: Type.Object({
      description: Type.String({
        description: "What should happen next? Describe the next action clearly.",
      }),
      priority: Type.Optional(
        Type.Number({
          description: "Priority 0-5 (0=normal, 5=urgent)",
          default: 0,
        })
      ),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      if (!dbReady) {
        return { content: [{ type: "text", text: "⚠ RAG database not available." }], details: {} };
      }

      const ns = rag.addNextStep(
        params.description,
        params.priority ?? 0,
        state.sessionId
      );

      if (ns) {
        state.whatWorked.push(`Next step: ${params.description.slice(0, 60)}`);
        return {
          content: [{ type: "text", text: `➡️ N+1 recorded: "${params.description}" (priority: ${params.priority ?? 0})` }],
          details: { nextStepId: ns.id },
        };
      }

      return { content: [{ type: "text", text: "❌ Failed to save next step" }], details: {}, isError: true };
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
    description: "Show RAG memory status including N+1 next steps",
    handler: async (_args, ctx) => {
      const agentId = getAgentId();
      const tasks = rag.getPendingTasks(agentId);
      const nextSteps = rag.getPendingNextSteps(agentId);
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
      if (nextSteps.length > 0) {
        lines.push(`   N+1 next steps (${nextSteps.length}):`);
        for (const ns of nextSteps) {
          lines.push(`     ${ns.id}. ${ns.description}`);
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
    description: "End the current RAG session — triggers LLM to generate a summary: /rag-end [notes]",
    handler: async (args, ctx) => {
      if (state.sessionId === null) {
        ctx.ui.notify("No active RAG session", "warning");
        return;
      }

      // Don't end immediately — ask the LLM to review the conversation
      // and generate a proper structured summary via rag_end_session tool.
      const userNotes = args.trim()
        ? `\n\nAdditional notes from user:\n${args.trim()}`
        : '';

      ctx.ui.notify(`🧠 Reviewing session #${state.sessionId} to generate summary...`, "info");

      pi.sendUserMessage(
        `[RAG End Session] The user wants to end this RAG session (session #${state.sessionId}). ` +
        `Please review the conversation above and generate a proper structured summary, ` +
        `then call the \`rag_end_session\` tool with the following fields:\n\n` +
        `- **summary**: A comprehensive summary of what was accomplished this session\n` +
        `- **whatWorked**: Comma-separated list of things that went well or were completed\n` +
        `- **whatFailed**: Comma-separated list of things that failed, are blocked, or need follow-up` +
        userNotes,
        { triggerTurn: true }
      );
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
      // Also prompt user about N+1
      if (ok && status === "success") {
        ctx.ui.notify("💡 Tip: use /rag-next <description> to set what comes next (N+1)", "info");
      }
    },
  });

  pi.registerCommand("rag-next", {
    description: "Set the next step (N+1): /rag-next <description> [priority]",
    handler: async (args, ctx) => {
      const parts = args.trim().split(/\s+/);
      const prio = parseInt(parts[parts.length - 1], 10);
      const hasPrio = !isNaN(prio) && parts.length > 1;
      const description = hasPrio ? parts.slice(0, -1).join(" ") : args.trim();

      if (!description) {
        ctx.ui.notify("Usage: /rag-next <what should happen next> [priority]", "warning");
        return;
      }

      const ns = rag.addNextStep(description, hasPrio ? prio : 0, state.sessionId);
      if (ns) {
        ctx.ui.notify(`➡️ N+1: "${description}" saved${hasPrio ? ` (priority ${prio})` : ""}`, "info");
      } else {
        ctx.ui.notify("❌ Failed to save next step", "error");
      }
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
