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

export interface RagStatus {
  agent_id: string;
  active_session: number | null;
  pending_tasks: RagTask[];
}

export interface RagSearchResult {
  notes: RagNote[];
  sessions: RagSession[];
}

// ── Python helper runner ────────────────────────────────────────────

function pyCode(code: string): string {
  const script = `
import sys, json
sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))})
from db import ${code}
`;
  try {
    return execSync(`${VENV_PYTHON} -c ${JSON.stringify(script)}`, {
      encoding: "utf-8",
      timeout: 10_000,
    }).trim();
  } catch (e: any) {
    console.error(`[rag-bridge] Python error: ${e.message}`);
    return "[]";
  }
}

// ── Public API ──────────────────────────────────────────────────────

export function dbExists(): boolean {
  return fs.existsSync(DB_PATH);
}

export function searchNotes(query: string, limit = 5): RagNote[] {
  const code = `
notes = search_notes(${JSON.stringify(query)}, ${limit})
print(json.dumps([dict(n) for n in notes]))
`;
  try {
    const raw = execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import search_notes; notes = search_notes(${JSON.stringify(query)}, ${limit}); print(json.dumps([dict(n) for n in notes]))`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    ).trim();
    return JSON.parse(raw) as RagNote[];
  } catch {
    return [];
  }
}

export function searchSessions(query: string, limit = 5): RagSession[] {
  try {
    const raw = execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import search_sessions; ss = search_sessions(${JSON.stringify(query)}, ${limit}); print(json.dumps([dict(s) for s in ss]))`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    ).trim();
    return JSON.parse(raw) as RagSession[];
  } catch {
    return [];
  }
}

export function addNote(
  agentId: string,
  title: string,
  content: string,
  tags: string[] = [],
  importance = 1
): RagNote | null {
  try {
    const raw = execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import add_note; n = add_note(${JSON.stringify(agentId)}, ${JSON.stringify(title)}, ${JSON.stringify(content)}, ${JSON.stringify(tags)}, ${importance}); print(json.dumps(dict(n)))`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    ).trim();
    return JSON.parse(raw) as RagNote;
  } catch {
    return null;
  }
}

export function startSession(agentId: string): number | null {
  try {
    const raw = execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import start_session; sid = start_session(${JSON.stringify(agentId)}); print(sid)`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    ).trim();
    return parseInt(raw, 10);
  } catch {
    return null;
  }
}

export function endSession(
  sessionId: number,
  summary: string,
  whatWorked: string[] = [],
  whatFailed: string[] = [],
  tokenCount = 0
): boolean {
  try {
    execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import end_session; end_session(${sessionId}, ${JSON.stringify(summary)}, ${JSON.stringify(whatWorked)}, ${JSON.stringify(whatFailed)}, token_count=${tokenCount}); print("ok")`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    );
    return true;
  } catch {
    return false;
  }
}

export function getPendingTasks(agentId: string): RagTask[] {
  try {
    const raw = execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import get_pending_tasks; tasks = get_pending_tasks(${JSON.stringify(agentId)}); print(json.dumps([dict(t) for t in tasks]))`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    ).trim();
    return JSON.parse(raw) as RagTask[];
  } catch {
    return [];
  }
}

export function getAgent(agentId: string): Record<string, any> | null {
  try {
    const raw = execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import get_agent; a = get_agent(${JSON.stringify(agentId)}); print(json.dumps(dict(a)) if a else "null")`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    ).trim();
    return raw === "null" ? null : JSON.parse(raw);
  } catch {
    return null;
  }
}

export function listAgents(): Record<string, any>[] {
  try {
    const raw = execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys, json; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import list_agents; agents = list_agents(); print(json.dumps([dict(a) for a in agents]))`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    ).trim();
    return JSON.parse(raw) as Record<string, any>[];
  } catch {
    return [];
  }
}

export function saveCheckpoint(
  sessionId: number | null,
  taskId: string,
  step: number,
  status = "running"
): boolean {
  try {
    execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import save_checkpoint; save_checkpoint(${sessionId}, ${JSON.stringify(taskId)}, ${step}, ${JSON.stringify(status)}); print("ok")`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    );
    return true;
  } catch {
    return false;
  }
}

export function buildRuntimePrompt(agentId: string, maxTokens = 6000): string | null {
  try {
    const raw = execSync(
      `${VENV_PYTHON} -c ${JSON.stringify(
        `import sys; sys.path.insert(0, ${JSON.stringify(path.join(RAG_DIR, "scripts"))}); from db import build_runtime_prompt; prompt = build_runtime_prompt(${JSON.stringify(agentId)}, ${maxTokens}); print(prompt)`
      )}`,
      {
        encoding: "utf-8",
        timeout: 10_000,
      }
    );
    return raw;
  } catch {
    return null;
  }
}
