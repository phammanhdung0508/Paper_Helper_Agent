import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { DATA_DIR } from "./paths";

export type LLMDebugEntry = {
  id: string;
  createdAt: string;
  source: "frontend";
  task: string;
  provider: string;
  model?: string;
  mode?: string;
  threadId?: string | null;
  promptHash: string;
  prompt?: string;
  rawResponse?: string;
  parsedResponse?: string;
  success: boolean;
  errorKind?: string;
  errorMessage?: string;
  usage?: unknown;
  fallbackReason?: string;
  codexFallbackUsed?: boolean;
};

const DEBUG_DIR = path.join(DATA_DIR, "debug");
export const LLM_DEBUG_LOG_PATH = path.join(DEBUG_DIR, "llm-responses.jsonl");

export function isLLMDebugEnabled(): boolean {
  return process.env.DEBUG_LLM_RESPONSES === "1";
}

export function redactSecrets(value: unknown): string | undefined {
  if (value == null) return undefined;
  let text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  text = text.replace(/(OPENAI_API_KEY|GEMINI_API_KEY|OPENROUTER_API_KEY|LANGFUSE_SECRET_KEY)\s*=\s*[^\s]+/gi, "$1=[REDACTED]");
  text = text.replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "[REDACTED]");
  text = text.replace(/sk-[A-Za-z0-9_-]{12,}/g, "[REDACTED]");
  text = text.replace(/gho_[A-Za-z0-9_]{12,}/g, "[REDACTED]");
  return text;
}

function hashPrompt(prompt: string): string {
  return crypto.createHash("sha256").update(prompt).digest("hex").slice(0, 32);
}

export function logFrontendLLMDebug(entry: {
  task?: string;
  provider?: string;
  model?: string;
  mode?: string;
  threadId?: string | null;
  prompt: string;
  rawResponse?: unknown;
  parsedResponse?: unknown;
  success: boolean;
  errorKind?: string;
  errorMessage?: unknown;
  usage?: unknown;
  fallbackReason?: string;
  codexFallbackUsed?: boolean;
}) {
  if (!isLLMDebugEnabled()) return;
  try {
    fs.mkdirSync(DEBUG_DIR, { recursive: true });
    const record: LLMDebugEntry = {
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
      source: "frontend",
      task: entry.task ?? "codex.runJson",
      provider: entry.provider ?? "codex-sdk",
      model: entry.model,
      mode: entry.mode,
      threadId: entry.threadId,
      promptHash: hashPrompt(entry.prompt),
      prompt: redactSecrets(entry.prompt),
      rawResponse: redactSecrets(entry.rawResponse),
      parsedResponse: redactSecrets(entry.parsedResponse),
      success: entry.success,
      errorKind: entry.errorKind,
      errorMessage: redactSecrets(entry.errorMessage),
      usage: entry.usage,
      fallbackReason: entry.fallbackReason,
      codexFallbackUsed: entry.codexFallbackUsed,
    };
    fs.appendFileSync(LLM_DEBUG_LOG_PATH, `${JSON.stringify(record)}\n`, "utf-8");
  } catch (e) {
    console.warn("[llm-debug] failed to write log", e);
  }
}

export function readLLMDebugEntries(limit = 100): LLMDebugEntry[] {
  if (!isLLMDebugEnabled() || !fs.existsSync(LLM_DEBUG_LOG_PATH)) return [];
  const lines = fs.readFileSync(LLM_DEBUG_LOG_PATH, "utf-8").trim().split("\n").filter(Boolean);
  return lines
    .slice(Math.max(0, lines.length - limit))
    .reverse()
    .map((line) => JSON.parse(line) as LLMDebugEntry);
}
