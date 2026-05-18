/**
 * rag-bridge.ts — Shared RAG DB bridge for pi-code extension
 *
 * Wraps the simple-rag-arch SQLite database for use from TypeScript.
 * Uses child_process to call the existing Python scripts/db.py functions.
 */

import { execSync } from "node:child_process";
import * as path from "node:path";
import * as fs from "node:fs";

const RAG_DIR = path.resolve(process.env.HOME || "~", "simple-rag-arch");
const DB_PATH = path.join(RAG_DIR, "memory", "memory.db");
const VENV_PYTHON = path.join(RAG_DIR, ".venv", "bin", "python3");

export interface RagNote {
  id: number;
  agent_id: string;
  title: string;
  content: string;
  importance: number;
  tags: string;
  created_at: string;
}

export interface RagSession {
  id: number;
  agent_id: string;
  summary: string | null;
  what_worked: string | null;
  what_failed: string | null;
  duration_s: number | null;
  token_count: number;
  created_at: string;
  ended_at: string | null;
}

export interface RagTask {
  id: number;
  session_id: number | null;
  task_id: string;
  step: number;
  status: string;
  retry_count: number;
}

export interface RagNextStep {
  id: number;
  session_id: number | null;
  description: string;
  priority: number;
  status: string;
  created_at: string;
}

// ── Helper: run Python against the RAG DB ───────────────────────────

function runPy(oneLiner: string): string | null {
  try {
    return execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); ${oneLiner}`
      )}`,
      { encoding: "utf-8", timeout: 10_000 }
    ).trim();
  } catch (e: any) {
    console.error(`[rag-bridge] Python error: ${e.message}`);
    return null;
  }
}

// ── Public API ──────────────────────────────────────────────────────

export function dbExists(): boolean {
  return fs.existsSync(DB_PATH);
}

export function searchNotes(query: string, limit = 5): RagNote[] {
  const raw = runPy(
    `from db import search_notes; notes = search_notes(${JSON.stringify(query)}, ${limit}); print(json.dumps([dict(n) for n in notes]))`
  );
  if (!raw) return [];
  try { return JSON.parse(raw) as RagNote[]; } catch { return []; }
}

export function searchSessions(query: string, limit = 5): RagSession[] {
  const raw = runPy(
    `from db import search_sessions; ss = search_sessions(${JSON.stringify(query)}, ${limit}); print(json.dumps([dict(s) for s in ss]))`
  );
  if (!raw) return [];
  try { return JSON.parse(raw) as RagSession[]; } catch { return []; }
}

export function addNote(
  agentId: string, title: string, content: string,
  tags: string[] = [], importance = 1
): RagNote | null {
  const raw = runPy(
    `from db import add_note; n = add_note(${JSON.stringify(agentId)}, ${JSON.stringify(title)}, ${JSON.stringify(content)}, ${JSON.stringify(tags)}, ${importance}); print(json.dumps(dict(n)))`
  );
  if (!raw) return null;
  try { return JSON.parse(raw) as RagNote; } catch { return null; }
}

export function startSession(agentId: string): number | null {
  const raw = runPy(
    `from db import start_session; sid = start_session(${JSON.stringify(agentId)}); print(sid)`
  );
  if (!raw) return null;
  const n = parseInt(raw, 10);
  return Number.isNaN(n) ? null : n;
}

export function endSession(
  sessionId: number, summary: string,
  whatWorked: string[] = [], whatFailed: string[] = [],
  tokenCount = 0
): boolean {
  const raw = runPy(
    `from db import end_session; end_session(${sessionId}, ${JSON.stringify(summary)}, ${JSON.stringify(whatWorked)}, ${JSON.stringify(whatFailed)}, token_count=${tokenCount}); print("ok")`
  );
  return raw === "ok";
}

export function getPendingTasks(agentId: string): RagTask[] {
  const raw = runPy(
    `from db import get_pending_tasks; tasks = get_pending_tasks(${JSON.stringify(agentId)}); print(json.dumps([dict(t) for t in tasks]))`
  );
  if (!raw) return [];
  try { return JSON.parse(raw) as RagTask[]; } catch { return []; }
}

export function getAgent(agentId: string): Record<string, any> | null {
  const raw = runPy(
    `from db import get_agent; a = get_agent(${JSON.stringify(agentId)}); print(json.dumps(dict(a)) if a else "null")`
  );
  if (!raw || raw === "null") return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export function listAgents(): Record<string, any>[] {
  const raw = runPy(
    `from db import list_agents; agents = list_agents(); print(json.dumps([dict(a) for a in agents]))`
  );
  if (!raw) return [];
  try { return JSON.parse(raw) as Record<string, any>[]; } catch { return []; }
}

export function getRecentSessions(agentId: string, limit = 3): RagSession[] {
  const raw = runPy(
    `from db import get_recent_sessions; ss = get_recent_sessions(${JSON.stringify(agentId)}, ${limit}); print(json.dumps([dict(s) for s in ss]))`
  );
  if (!raw) return [];
  try { return JSON.parse(raw) as RagSession[]; } catch { return []; }
}

export function saveCheckpoint(
  sessionId: number | null, taskId: string, step: number, status = "running"
): boolean {
  const raw = runPy(
    `from db import save_checkpoint; save_checkpoint(${sessionId ?? "None"}, ${JSON.stringify(taskId)}, ${step}, ${JSON.stringify(status)}); print("ok")`
  );
  return raw === "ok";
}

export function buildRuntimePrompt(agentId: string, maxTokens = 6000): string | null {
  return runPy(
    `from db import build_runtime_prompt; prompt = build_runtime_prompt(${JSON.stringify(agentId)}, ${maxTokens}); print(prompt)`
  );
}

// ── N+1 Next Step Tracking ──────────────────────────────────────────

export interface RagNextStep {
  id: number;
  session_id: number | null;
  description: string;
  priority: number;
  status: string;
  created_at: string;
}

/**
 * Record a next-step action. Returns the new next_step row or null.
 */
export function addNextStep(
  description: string,
  priority = 0,
  sessionId: number | null = null
): RagNextStep | null {
  const raw = runPy(
    `from db import add_next_step; ns = add_next_step(${sessionId ?? "None"}, ${JSON.stringify(description)}, ${priority}); print(json.dumps(dict(ns)))`
  );
  if (!raw) return null;
  try { return JSON.parse(raw) as RagNextStep; } catch { return null; }
}

/**
 * Get pending next steps for an agent, ordered by priority then creation date.
 */
export function getPendingNextSteps(agentId: string, limit = 10): RagNextStep[] {
  const raw = runPy(
    `from db import get_pending_next_steps; steps = get_pending_next_steps(${JSON.stringify(agentId)}, ${limit}); print(json.dumps([dict(s) for s in steps]))`
  );
  if (!raw) return [];
  try { return JSON.parse(raw) as RagNextStep[]; } catch { return []; }
}

/**
 * Mark a next step as completed.
 */
export function completeNextStep(nextStepId: number): boolean {
  const raw = runPy(
    `from db import complete_next_step; complete_next_step(${nextStepId}); print("ok")`
  );
  return raw === "ok";
}
