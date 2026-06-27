import { Codex, type ThreadOptions } from "@openai/codex-sdk";
import { Langfuse } from "langfuse";
import { CODEX_SCRATCH_DIR } from "./paths";
import { logFrontendLLMDebug, redactSecrets } from "./llm-debug";
import { readAccountInfo } from "./codex-account";
import { runOpenRouterJson } from "./openrouter";
import { runGroqJson } from "./groq";
import { serverEnv, serverEnvFlag } from "./server-env";

let _codex: Codex | null = null;
function getCodex(): Codex {
  if (_codex) return _codex;
  const codexPathOverride = process.env.CODEX_BINARY_PATH;
  _codex = new Codex({
    ...(codexPathOverride ? { codexPathOverride } : {}),
    config: { tools: { image_gen: false } },
  });
  return _codex;
}

export type RunOptions = {
  reasoning?: "low" | "medium" | "high";
  webSearch?: boolean;
  signal?: AbortSignal;
  threadOverrides?: Partial<ThreadOptions>;
  debugTask?: string;
  task?: string;
};

type CodexThread = {
  id?: string | null;
  run: (
    prompt: string,
    options: { outputSchema: object; signal?: AbortSignal },
  ) => Promise<{ finalResponse?: string; usage: unknown }>;
};

function threadOptions(opts: RunOptions = {}): ThreadOptions {
  return {
    sandboxMode: "read-only",
    approvalPolicy: "never",
    skipGitRepoCheck: true,
    workingDirectory: CODEX_SCRATCH_DIR,
    modelReasoningEffort: opts.reasoning ?? "low",
    webSearchEnabled: opts.webSearch ?? false,
    ...(opts.threadOverrides ?? {}),
  };
}

function assertCodexEnabled() {
  if (!serverEnvFlag("ENABLE_CODEX", false)) {
    throw new CodexError("generic", "Codex is disabled by ENABLE_CODEX=false.");
  }
}

function parseTurnJson<T>(finalResponse: string | undefined): T {
  const text = finalResponse?.trim();
  if (!text) throw new Error("Empty finalResponse from codex");
  const cleaned = text.replace(/^```(?:json)?\s*/i, "").replace(/```$/i, "").trim();
  return JSON.parse(cleaned) as T;
}

export type CodexErrorKind = "auth_lost" | "rate_limit" | "binary_missing" | "generic";

export class CodexError extends Error {
  readonly kind: CodexErrorKind;
  readonly retryAt?: number;
  readonly window?: "5h" | "weekly" | "unknown";
  constructor(kind: CodexErrorKind, message: string, extras?: { retryAt?: number; window?: "5h" | "weekly" | "unknown" }) {
    super(message);
    this.name = "CodexError";
    this.kind = kind;
    this.retryAt = extras?.retryAt;
    this.window = extras?.window;
  }
}

export type CodexHealth = {
  ok: boolean;
  kind: CodexErrorKind | null;
  message: string | null;
  retryAt: number | null;
  window: "5h" | "weekly" | "unknown" | null;
  serial: number;
  lastOkAt: number | null;
};

declare global {
  // eslint-disable-next-line no-var
  var __getitCodexHealth: CodexHealth | undefined;
}

const _initialHealth: CodexHealth = {
  ok: true,
  kind: null,
  message: null,
  retryAt: null,
  window: null,
  serial: 0,
  lastOkAt: null,
};

const health: CodexHealth = globalThis.__getitCodexHealth ?? (globalThis.__getitCodexHealth = { ..._initialHealth });

export function getCodexHealth(): CodexHealth {
  if (health.kind === "rate_limit" && health.retryAt != null && Date.now() >= health.retryAt) {
    Object.assign(health, _initialHealth, { serial: health.serial });
  }
  return { ...health };
}

function markOk() {
  if (!health.ok) {
    Object.assign(health, _initialHealth, { serial: health.serial + 1 });
  }
  health.lastOkAt = Date.now();
  health.ok = true;
}

function markError(err: CodexError) {
  health.ok = false;
  health.kind = err.kind;
  health.message = err.message;
  health.retryAt = err.retryAt ?? null;
  health.window = err.window ?? null;
  health.serial += 1;
}

function preflightHealth(): CodexError | null {
  if (health.kind === "rate_limit" && health.retryAt != null && Date.now() < health.retryAt) {
    return new CodexError("rate_limit", health.message ?? "Rate limit active", {
      retryAt: health.retryAt,
      window: health.window ?? "unknown",
    });
  }
  return null;
}

// Grouped Regex patterns
const ERR_PATTERNS = {
  RATE_LIMIT: /(rate.?limit|usage limit|too many requests|429|quota|you've hit|you have hit)/i,
  AUTH: /(not logged in|please.*log ?in|unauthori[sz]ed|401|invalid api key|token (?:has )?expired|sign in)/i,
  BINARY: /(unable to locate codex|cannot find module|enoent.*codex|codex.*not found|spawn .* enoent)/i,
  TIME: /try again in\s*(\d+(?:\.\d+)?)\s*(s|ms|seconds?|m|mins?|minutes?|h|hrs?|hours?)/i,
  WEEKLY: /\bweekly\b/i,
  FIVE_H: /\b(5\s*h|5\s*hour|five hour)\b/i
};

export function classifyCodexError(err: unknown): CodexError {
  const msg = err instanceof Error ? err.message : typeof err === "string" ? err : "Codex call failed";

  if (ERR_PATTERNS.BINARY.test(msg)) return new CodexError("binary_missing", msg);
  if (ERR_PATTERNS.AUTH.test(msg)) return new CodexError("auth_lost", msg);

  if (ERR_PATTERNS.RATE_LIMIT.test(msg)) {
    let retryAt: number | undefined;
    const timeMatch = ERR_PATTERNS.TIME.exec(msg);

    if (timeMatch) {
      const value = Number(timeMatch[1]);
      const unit = timeMatch[2].toLowerCase();
      let ms = 0;

      if (unit.startsWith("ms")) ms = value;
      else if (unit.startsWith("s")) ms = value * 1000;
      else if (unit.startsWith("m")) ms = value * 60_000;
      else if (unit.startsWith("h")) ms = value * 3_600_000;

      retryAt = Date.now() + ms;
    }

    const window = ERR_PATTERNS.WEEKLY.test(msg) ? "weekly" : ERR_PATTERNS.FIVE_H.test(msg) ? "5h" : "unknown";
    return new CodexError("rate_limit", msg, { retryAt, window });
  }

  return new CodexError("generic", msg);
}

let _langfuse: Langfuse | null = null;
function getLangfuseClient(): Langfuse | null {
  if (_langfuse) return _langfuse;
  const publicKey = serverEnv("LANGFUSE_PUBLIC_KEY");
  const secretKey = serverEnv("LANGFUSE_SECRET_KEY");
  const baseUrl = serverEnv("LANGFUSE_HOST") || "https://cloud.langfuse.com";
  if (!publicKey || !secretKey) return null;
  _langfuse = new Langfuse({ publicKey, secretKey, baseUrl });
  return _langfuse;
}

interface TokenUsage {
  promptTokens?: number;
  prompt_tokens?: number;
  input_tokens?: number;
  completionTokens?: number;
  completion_tokens?: number;
  output_tokens?: number;
  totalTokens?: number;
  total_tokens?: number;
  [key: string]: unknown;
}

function parseUsage(usageObj?: TokenUsage | null) {
  if (!usageObj) return undefined;
  return {
    promptTokens: usageObj.promptTokens || usageObj.prompt_tokens || usageObj.input_tokens,
    completionTokens: usageObj.completionTokens || usageObj.completion_tokens || usageObj.output_tokens,
    totalTokens: usageObj.totalTokens || usageObj.total_tokens,
  };
}

function logToLangfuse(args: { task: string; prompt: string; response?: string; success: boolean; error?: string; usage?: unknown }) {
  const lf = getLangfuseClient();
  if (!lf) return;
  try {
    const account = readAccountInfo();
    lf.generation({
      name: `codex-${args.task}`,
      model: "codex-cli",
      input: redactSecrets(args.prompt),
      output: redactSecrets(args.response || args.error),
      usage: parseUsage(args.usage as TokenUsage),
      metadata: {
        authMode: account?.authMode ?? null,
        planType: account?.planType ?? null,
        status: args.success ? "success" : "failed",
      },
    });
    lf.flushAsync().catch(() => {});
  } catch (e) {
    console.warn("Failed to log frontend trace to Langfuse:", e);
  }
}

// ── Helpers ─────────────────────────────────────────────────────────────

function isBatchTask(taskName: string): boolean {
  return [
    "extract_knowledge_graph",
    "concept_detection",
    "generate_visual_spec"
  ].includes(taskName) ||
  taskName.includes("detect") ||
  taskName.includes("extract") ||
  taskName.includes("generate_viz") ||
  taskName.includes("repair_viz") ||
  taskName.includes("evaluate");
}

function shouldBypassOpenRouter(taskName: string, isWebSearch: boolean): boolean {
  return isWebSearch || taskName === "feynman_gen" || taskName.includes("feynman") || taskName.includes("chat");
}

function classifyUpstreamErrorKind(message: string): CodexErrorKind {
  const lower = message.toLowerCase();
  if (message.includes("429") || lower.includes("rate limit") || lower.includes("too many requests")) return "rate_limit";
  if (message.includes("401") || message.includes("403") || lower.includes("api key") || lower.includes("auth")) return "auth_lost";
  return "generic";
}

async function executeCodexAttempt<T>(args: {
  thread: CodexThread;
  prompt: string;
  outputSchema: object;
  opts: RunOptions;
  taskName: string;
  logMode: "single" | "start" | "resume";
  debugTaskName: string;
  overrideThreadId?: string;
}): Promise<{ data: T; usage: unknown; threadId: string }> {
  let rawResponse: string | undefined;
  try {
    const turn = await args.thread.run(args.prompt, {
      outputSchema: args.outputSchema,
      signal: args.opts.signal,
    });
    rawResponse = turn.finalResponse;
    const parsed = parseTurnJson<T>(rawResponse);
    markOk();

    const threadId = args.thread.id ?? args.overrideThreadId ?? "unknown-thread";

    logToLangfuse({
      task: args.debugTaskName,
      prompt: args.prompt,
      response: rawResponse,
      success: true,
      usage: turn.usage,
    });
    logFrontendLLMDebug({
      task: args.debugTaskName,
      provider: "codex-sdk",
      model: "codex-cli",
      mode: args.logMode,
      threadId,
      prompt: args.prompt,
      rawResponse,
      parsedResponse: parsed,
      success: true,
      usage: turn.usage,
    });

    return { data: parsed, usage: turn.usage, threadId };
  } catch (err) {
    const classified = classifyCodexError(err);
    const threadId = args.thread.id ?? args.overrideThreadId ?? "unknown-thread";

    logToLangfuse({
      task: args.debugTaskName,
      prompt: args.prompt,
      error: classified.message,
      success: false,
    });
    logFrontendLLMDebug({
      task: args.debugTaskName,
      provider: "codex-sdk",
      model: "codex-cli",
      mode: args.logMode,
      threadId,
      prompt: args.prompt,
      rawResponse,
      success: false,
      errorKind: classified.kind,
      errorMessage: classified.message,
    });

    throw classified; // Bubble up the classified error
  }
}

// ── Core API ────────────────────────────────────────────────────────────

export async function runJson<T>(
  prompt: string,
  outputSchema: object,
  opts: RunOptions = {},
): Promise<{ data: T; usage: unknown }> {
  const taskName = opts.task ?? opts.debugTask ?? "unknown";
  const groqApiKey = serverEnv("GROQ_API_KEY");
  const allowGroq = serverEnvFlag("ENABLE_GROQ", true);
  const openrouterApiKey = serverEnv("OPENROUTER_API_KEY");
  const allowOpenRouterFallback = serverEnvFlag("ENABLE_OPENROUTER_FALLBACK", false);
  const bypassOpenRouter = shouldBypassOpenRouter(taskName, opts.webSearch === true);
  let upstreamError: CodexError | null = null;

  if (allowGroq && groqApiKey && !bypassOpenRouter) {
    try {
      const groqResult = await runGroqJson<T>(taskName, prompt, outputSchema, opts.signal);
      logFrontendLLMDebug({
        task: taskName,
        provider: "groq",
        model: groqResult.model,
        mode: "single",
        prompt,
        rawResponse: JSON.stringify(groqResult.data),
        parsedResponse: groqResult.data,
        success: true,
        usage: groqResult.usage,
      });
      return { data: groqResult.data, usage: groqResult.usage };
    } catch (groqErr: unknown) {
      const errMsg = groqErr instanceof Error ? groqErr.message : String(groqErr);
      console.warn(`[Groq] All models failed for task '${taskName}': ${errMsg}`);
      logFrontendLLMDebug({ task: taskName, provider: "groq", mode: "single", prompt, success: false, errorKind: "groq_failed", errorMessage: errMsg });
      upstreamError = new CodexError(classifyUpstreamErrorKind(errMsg), `Groq failed: ${errMsg}`);
    }
  }

  if (openrouterApiKey && !bypassOpenRouter && allowOpenRouterFallback) {
    try {
      const orResult = await runOpenRouterJson<T>(taskName, prompt, outputSchema, opts.signal);
      logFrontendLLMDebug({
        task: taskName,
        provider: "openrouter",
        model: orResult.model,
        mode: "single",
        prompt,
        rawResponse: JSON.stringify(orResult.data),
        parsedResponse: orResult.data,
        success: true,
        usage: orResult.usage,
      });
      return { data: orResult.data, usage: orResult.usage };
    } catch (orErr: unknown) {
      const errMsg = orErr instanceof Error ? orErr.message : String(orErr);
      console.warn(`[OpenRouter] All models failed for task '${taskName}': ${errMsg}`);
      upstreamError = new CodexError(classifyUpstreamErrorKind(errMsg), `OpenRouter failed: ${errMsg}`);

      const isBatch = isBatchTask(taskName);
      const fallbackAllowed = isBatch
        ? serverEnvFlag("ENABLE_CODEX_FALLBACK_FOR_BATCH", false)
        : serverEnvFlag("ENABLE_CODEX_FALLBACK_FOR_INTERACTIVE", false);

      logFrontendLLMDebug({ task: taskName, provider: "openrouter", mode: "single", prompt, success: false, errorKind: "openrouter_failed", errorMessage: errMsg });

      if (!fallbackAllowed) {
        console.warn(`[LLM Router] Codex fallback disabled for task '${taskName}' (isBatch=${isBatch}). Aborting.`);
        throw new CodexError("rate_limit", `OpenRouter failed, and Codex fallback is disabled: ${errMsg}`);
      }
      console.log(`[LLM Router] Falling back to Codex for task '${taskName}'...`);
    }
  }

  if (!serverEnvFlag("ENABLE_CODEX", false) && upstreamError) {
    throw upstreamError;
  }

  assertCodexEnabled();
  const preflight = preflightHealth();
  if (preflight) throw preflight;

  let lastErr: CodexError | null = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const thread = getCodex().startThread(threadOptions(opts));
      const res = await executeCodexAttempt<T>({
        thread,
        prompt,
        outputSchema,
        opts,
        taskName,
        logMode: "single",
        debugTaskName: taskName
      });
      return { data: res.data, usage: res.usage };
    } catch (err) {
      if (err instanceof CodexError) {
        lastErr = err;
        if (err.kind !== "generic") {
          markError(err);
          throw err;
        }
      } else {
        lastErr = classifyCodexError(err);
        markError(lastErr);
        throw lastErr;
      }
    }
  }
  if (lastErr && lastErr.kind !== "generic") markError(lastErr);
  throw lastErr;
}

export async function runJsonInThread<T>(args: {
  outputSchema: object;
  opts?: RunOptions;
  resume?: { threadId: string; input: string };
  start?: { input: string };
}): Promise<{ data: T; usage: unknown; threadId: string | null }> {
  assertCodexEnabled();
  const preflight = preflightHealth();
  if (preflight) throw preflight;

  const opts = args.opts ?? {};

  if (args.resume) {
    try {
      const thread = getCodex().resumeThread(args.resume.threadId, threadOptions(opts));
      const res = await executeCodexAttempt<T>({
        thread,
        prompt: args.resume.input,
        outputSchema: args.outputSchema,
        opts,
        taskName: opts.debugTask ?? "runJsonInThread-resume",
        logMode: "resume",
        debugTaskName: opts.debugTask ?? "codex.runJsonInThread",
        overrideThreadId: args.resume.threadId
      });
      return { data: res.data, usage: res.usage, threadId: args.resume.threadId };
    } catch (err) {
      if (err instanceof CodexError && err.kind !== "generic") markError(err);
      throw err;
    }
  }

  if (!args.start) throw new Error("runJsonInThread: provide `start` or `resume`");

  let lastErr: CodexError | null = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const thread = getCodex().startThread(threadOptions(opts));
      return await executeCodexAttempt<T>({
        thread,
        prompt: args.start.input,
        outputSchema: args.outputSchema,
        opts,
        taskName: opts.debugTask ?? "runJsonInThread-start",
        logMode: "start",
        debugTaskName: opts.debugTask ?? "codex.runJsonInThread"
      });
    } catch (err) {
      if (err instanceof CodexError) {
        lastErr = err;
        if (err.kind !== "generic") {
          markError(err);
          throw err;
        }
      } else {
        lastErr = classifyCodexError(err);
        markError(lastErr);
        throw lastErr;
      }
    }
  }

  if (lastErr && lastErr.kind !== "generic") markError(lastErr);
  throw lastErr;
}
