/**
 * Thin wrapper around @openai/codex-sdk that gives us:
 *   - lazily-initialized singleton
 *   - sane defaults for "answer-only" mode (read-only sandbox, no approvals,
 *     web search off by default)
 *   - a `runJson` helper that runs a one-shot turn against an output-schema
 *     and returns the parsed JSON, with retry-on-parse-failure
 *   - structured CodexError classification (auth lost vs rate-limit vs
 *     generic). Every agent call funnels through here, so the rest of the
 *     app gets a single, stable shape to display.
 *
 * Note on the Codex binary: in packaged Electron builds the main process
 * resolves the bundled binary and exposes its absolute path through
 * CODEX_BINARY_PATH. Passing that path to the SDK avoids fragile
 * node_modules lookup from the standalone Next server.
 */

import { Codex } from "@openai/codex-sdk";
import type { ThreadOptions } from "@openai/codex-sdk";
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
    config: {
      // disable image generation so we can use 'low' reasoning; the demo is
      // text-only so there is nothing to lose.
      tools: { image_gen: false },
    },
  });
  return _codex;
}

export type RunOptions = {
  /** Defaults to "low" — fastest answer-only model setting that allows tools=image_gen=false. */
  reasoning?: "low" | "medium" | "high";
  /** Allow live web search for this call (e.g. legal citations). */
  webSearch?: boolean;
  /** AbortSignal forwarded to the underlying child process. */
  signal?: AbortSignal;
  /** Override default thread options. */
  threadOverrides?: Partial<ThreadOptions>;
  /** Optional debug label for raw-response logging. */
  debugTask?: string;
  /** Formal task classification for model routing and fallback decisions. */
  task?: string;
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

function buildThread(opts: RunOptions = {}) {
  return getCodex().startThread(threadOptions(opts));
}

/** Strip markdown code fences the model sometimes wraps JSON in, then parse. */
function parseTurnJson<T>(finalResponse: string | undefined): T {
  const text = finalResponse?.trim();
  if (!text) throw new Error("Empty finalResponse from codex");
  const cleaned = text
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/```$/i, "")
    .trim();
  return JSON.parse(cleaned) as T;
}

/**
 * Error kinds that we want the UI to react to differently. Anything not
 * one of these stays `generic`; the calling code can still surface the
 * raw message but the banner won't claim a rate-limit when there isn't one.
 */
export type CodexErrorKind =
  | "auth_lost" // user is not logged in (or token revoked)
  | "rate_limit" // hit the 5h or weekly window
  | "binary_missing" // the codex binary itself can't be found
  | "generic";

export class CodexError extends Error {
  readonly kind: CodexErrorKind;
  /**
   * If `kind === "rate_limit"` and the model gave us a deadline,
   * `retryAt` is a unix-ms timestamp the UI can count down to. Optional;
   * the wrapper falls back to a phrased message when no deadline is
   * available.
   */
  readonly retryAt?: number;
  /**
   * Coarse window the rate limit belongs to, when the message tells us.
   * "5h" or "weekly" — the same labels the codex TUI uses. Falls back to
   * "unknown" if we can't tell.
   */
  readonly window?: "5h" | "weekly" | "unknown";

  constructor(
    kind: CodexErrorKind,
    message: string,
    extras?: { retryAt?: number; window?: "5h" | "weekly" | "unknown" },
  ) {
    super(message);
    this.name = "CodexError";
    this.kind = kind;
    this.retryAt = extras?.retryAt;
    this.window = extras?.window;
  }
}

// ── Health mailbox ──────────────────────────────────────────────────────
// Process-local snapshot of the most recent CodexError. The UI polls
// /api/codex/health to render a banner with a countdown + reconnect
// button. We also use it to short-circuit calls while a rate limit is
// still active — no point hammering the API.
export type CodexHealth = {
  ok: boolean;
  kind: CodexErrorKind | null;
  message: string | null;
  retryAt: number | null;
  window: "5h" | "weekly" | "unknown" | null;
  /** Monotone counter — UI uses this to detect "a new error came in" vs
   *  "still the same one I'm already showing". */
  serial: number;
  /** Last successful Codex call timestamp (epoch ms). */
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

const health: CodexHealth =
  globalThis.__getitCodexHealth ??
  (globalThis.__getitCodexHealth = { ..._initialHealth });

export function getCodexHealth(): CodexHealth {
  // If a rate-limit retry deadline has passed, auto-clear so the UI
  // stops showing the banner without a server round-trip.
  if (
    health.kind === "rate_limit" &&
    health.retryAt != null &&
    Date.now() >= health.retryAt
  ) {
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
  if (
    health.kind === "rate_limit" &&
    health.retryAt != null &&
    Date.now() < health.retryAt
  ) {
    return new CodexError("rate_limit", health.message ?? "Rate limit active", {
      retryAt: health.retryAt,
      window: health.window ?? "unknown",
    });
  }
  return null;
}

const RX_RATE_LIMIT =
  /(rate.?limit|usage limit|too many requests|429|quota|you've hit|you have hit)/i;
const RX_TRY_AGAIN_SECONDS = /try again in\s*(\d+(?:\.\d+)?)\s*(s|ms|seconds?)/i;
const RX_TRY_AGAIN_MIN = /try again in\s*(\d+(?:\.\d+)?)\s*(m|mins?|minutes?)/i;
const RX_TRY_AGAIN_HOUR = /try again in\s*(\d+(?:\.\d+)?)\s*(h|hrs?|hours?)/i;
const RX_AUTH = /(not logged in|please.*log ?in|unauthori[sz]ed|401|invalid api key|token (?:has )?expired|sign in)/i;
const RX_BINARY = /(unable to locate codex|cannot find module|enoent.*codex|codex.*not found|spawn .* enoent)/i;
const RX_WEEKLY = /\bweekly\b/i;
const RX_FIVE_H = /\b(5\s*h|5\s*hour|five hour)\b/i;

export function classifyCodexError(err: unknown): CodexError {
  const msg =
    err instanceof Error
      ? err.message
      : typeof err === "string"
        ? err
        : "Codex call failed";

  if (RX_BINARY.test(msg)) {
    return new CodexError("binary_missing", msg);
  }

  if (RX_AUTH.test(msg)) {
    return new CodexError("auth_lost", msg);
  }

  if (RX_RATE_LIMIT.test(msg)) {
    let retryAt: number | undefined;
    const sec = RX_TRY_AGAIN_SECONDS.exec(msg);
    const min = RX_TRY_AGAIN_MIN.exec(msg);
    const hr = RX_TRY_AGAIN_HOUR.exec(msg);
    if (sec) {
      const unit = sec[2].toLowerCase();
      const value = Number(sec[1]);
      const ms = unit.startsWith("ms") ? value : value * 1000;
      retryAt = Date.now() + ms;
    } else if (min) {
      retryAt = Date.now() + Number(min[1]) * 60_000;
    } else if (hr) {
      retryAt = Date.now() + Number(hr[1]) * 3_600_000;
    }
    const window: "5h" | "weekly" | "unknown" = RX_WEEKLY.test(msg)
      ? "weekly"
      : RX_FIVE_H.test(msg)
        ? "5h"
        : "unknown";
    return new CodexError("rate_limit", msg, { retryAt, window });
  }

  return new CodexError("generic", msg);
}

let _langfuse: Langfuse | null = null;
function getLangfuseClient(): Langfuse | null {
  if (_langfuse) return _langfuse;
  const publicKey = process.env.LANGFUSE_PUBLIC_KEY;
  const secretKey = process.env.LANGFUSE_SECRET_KEY;
  const baseUrl = process.env.LANGFUSE_HOST || "https://cloud.langfuse.com";
  if (!publicKey || !secretKey) return null;
  _langfuse = new Langfuse({ publicKey, secretKey, baseUrl });
  return _langfuse;
}

function logToLangfuse(args: {
  task: string;
  prompt: string;
  response?: string;
  success: boolean;
  error?: string;
  usage?: unknown;
}) {
  const lf = getLangfuseClient();
  if (!lf) return;
  try {
    const account = readAccountInfo();
    const usageObj = args.usage && typeof args.usage === "object" ? (args.usage as Record<string, unknown>) : null;
    const usage = usageObj ? {
      promptTokens: (usageObj.promptTokens as number) || (usageObj.prompt_tokens as number) || (usageObj.input_tokens as number) || undefined,
      completionTokens: (usageObj.completionTokens as number) || (usageObj.completion_tokens as number) || (usageObj.output_tokens as number) || undefined,
      totalTokens: (usageObj.totalTokens as number) || (usageObj.total_tokens as number) || undefined,
    } : undefined;

    lf.generation({
      name: `codex-${args.task}`,
      model: "codex-cli",
      input: redactSecrets(args.prompt),
      output: redactSecrets(args.response || args.error),
      usage,
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

/**
 * Run a single turn that must return JSON conforming to the supplied schema.
 * Retries once if the model returns un-parseable text. Throws CodexError on
 * failure so callers can pattern-match on `.kind`.
 */
export async function runJson<T>(
  prompt: string,
  outputSchema: object,
  opts: RunOptions = {},
): Promise<{ data: T; usage: unknown }> {
  const taskName = opts.task ?? opts.debugTask ?? "unknown";
  const groqApiKey = serverEnv("GROQ_API_KEY");
  const openrouterApiKey = serverEnv("OPENROUTER_API_KEY");
  const allowOpenRouterFallback = serverEnvFlag("ENABLE_OPENROUTER_FALLBACK", false);

  const isWebSearch = opts.webSearch === true;
  const isFeynman = taskName === "feynman_gen" || taskName.includes("feynman");
  const isChat = taskName.includes("chat");
  const bypassOpenRouter = isWebSearch || isFeynman || isChat;

  if (groqApiKey && !bypassOpenRouter) {
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
      logFrontendLLMDebug({
        task: taskName,
        provider: "groq",
        mode: "single",
        prompt,
        success: false,
        errorKind: "groq_failed",
        errorMessage: errMsg,
      });
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

      const isBatch = taskName === "extract_knowledge_graph" || taskName === "concept_detection" || taskName.includes("detect");
      const fallbackAllowed = isBatch
        ? process.env.ENABLE_CODEX_FALLBACK_FOR_BATCH === "true"
        : process.env.ENABLE_CODEX_FALLBACK_FOR_INTERACTIVE === "true";

      logFrontendLLMDebug({
        task: taskName,
        provider: "openrouter",
        mode: "single",
        prompt,
        success: false,
        errorKind: "openrouter_failed",
        errorMessage: errMsg,
      });

      if (!fallbackAllowed) {
        console.warn(`[LLM Router] Codex fallback disabled for task '${taskName}' (isBatch=${isBatch}). Aborting.`);
        throw new CodexError("rate_limit", `OpenRouter failed, and Codex fallback is disabled: ${errMsg}`);
      }

      console.log(`[LLM Router] Falling back to Codex for task '${taskName}'...`);
    }
  }

  // Short-circuit: if we know we're inside a rate-limit window, fail fast
  // without burning another Codex call.
  const preflight = preflightHealth();
  if (preflight) throw preflight;

  let lastErr: unknown = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    const thread = buildThread(opts);
    let rawResponse: string | undefined;
    try {
      const turn = await thread.run(prompt, {
        outputSchema,
        signal: opts.signal,
      });
      rawResponse = turn.finalResponse;
      const parsed = parseTurnJson<T>(rawResponse);
      markOk();
      logToLangfuse({
        task: taskName,
        prompt,
        response: rawResponse,
        success: true,
        usage: turn.usage,
      });
      logFrontendLLMDebug({
        task: taskName,
        provider: "codex-sdk",
        model: "codex-cli",
        mode: "single",
        threadId: thread.id,
        prompt,
        rawResponse,
        parsedResponse: parsed,
        success: true,
        usage: turn.usage,
      });
      return { data: parsed, usage: turn.usage };
    } catch (err) {
      lastErr = err;
      const classified = classifyCodexError(err);
      logToLangfuse({
        task: taskName,
        prompt,
        error: classified.message,
        success: false,
      });
      logFrontendLLMDebug({
        task: taskName,
        provider: "codex-sdk",
        model: "codex-cli",
        mode: "single",
        threadId: thread.id,
        prompt,
        rawResponse,
        success: false,
        errorKind: classified.kind,
        errorMessage: classified.message,
      });
      // Auth/rate-limit/binary failures: don't bother retrying — the
      // condition isn't going to clear in 200ms. Bubble up immediately so
      // the in-app banner can take over.
      if (classified.kind !== "generic") {
        markError(classified);
        throw classified;
      }
    }
  }
  const finalErr = classifyCodexError(lastErr);
  if (finalErr.kind !== "generic") markError(finalErr);
  throw finalErr;
}

/**
 * Thread-aware JSON runner for multi-turn tools (chat).
 *
 * Two modes, exactly one of which must be supplied:
 *   • start  — open a NEW thread and send the full first-turn prompt (system
 *              + document + history). Returns the new `threadId` to persist.
 *              Retries once on a parse blip, like runJson.
 *   • resume — continue an EXISTING thread by `threadId`, sending only the new
 *              turn input. The model still has the document + prior turns in
 *              its own context, so we don't resend them (and the stable prefix
 *              is a guaranteed cache hit). No internal retry: on any generic
 *              failure (including a lost/expired session) the caller falls
 *              back to `start` with full context, so a resume never silently
 *              degrades the answer.
 *
 * Rate-limit / auth / binary errors are classified and thrown immediately in
 * both modes so the health banner takes over.
 */
export async function runJsonInThread<T>(args: {
  outputSchema: object;
  opts?: RunOptions;
  resume?: { threadId: string; input: string };
  start?: { input: string };
}): Promise<{ data: T; usage: unknown; threadId: string | null }> {
  const preflight = preflightHealth();
  if (preflight) throw preflight;
  const opts = args.opts ?? {};

  if (args.resume) {
    const thread = getCodex().resumeThread(args.resume.threadId, threadOptions(opts));
    let rawResponse: string | undefined;
    try {
      const turn = await thread.run(args.resume.input, {
        outputSchema: args.outputSchema,
        signal: opts.signal,
      });
      rawResponse = turn.finalResponse;
      const parsed = parseTurnJson<T>(rawResponse);
      markOk();
      logToLangfuse({
        task: opts.debugTask ?? "runJsonInThread-resume",
        prompt: args.resume.input,
        response: rawResponse,
        success: true,
        usage: turn.usage,
      });
      logFrontendLLMDebug({
        task: opts.debugTask ?? "codex.runJsonInThread",
        mode: "resume",
        threadId: thread.id ?? args.resume.threadId,
        prompt: args.resume.input,
        rawResponse,
        parsedResponse: parsed,
        success: true,
        usage: turn.usage,
      });
      return { data: parsed, usage: turn.usage, threadId: thread.id ?? args.resume.threadId };
    } catch (err) {
      const classified = classifyCodexError(err);
      logToLangfuse({
        task: opts.debugTask ?? "runJsonInThread-resume",
        prompt: args.resume.input,
        error: classified.message,
        success: false,
      });
      logFrontendLLMDebug({
        task: opts.debugTask ?? "codex.runJsonInThread",
        mode: "resume",
        threadId: thread.id ?? args.resume.threadId,
        prompt: args.resume.input,
        rawResponse,
        success: false,
        errorKind: classified.kind,
        errorMessage: classified.message,
      });
      if (classified.kind !== "generic") markError(classified);
      throw classified;
    }
  }

  if (!args.start) throw new Error("runJsonInThread: provide `start` or `resume`");

  let lastErr: unknown = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    const thread = buildThread(opts);
    let rawResponse: string | undefined;
    try {
      const turn = await thread.run(args.start.input, {
        outputSchema: args.outputSchema,
        signal: opts.signal,
      });
      rawResponse = turn.finalResponse;
      const parsed = parseTurnJson<T>(rawResponse);
      markOk();
      logToLangfuse({
        task: opts.debugTask ?? "runJsonInThread-start",
        prompt: args.start.input,
        response: rawResponse,
        success: true,
        usage: turn.usage,
      });
      logFrontendLLMDebug({
        task: opts.debugTask ?? "codex.runJsonInThread",
        mode: "start",
        threadId: thread.id,
        prompt: args.start.input,
        rawResponse,
        parsedResponse: parsed,
        success: true,
        usage: turn.usage,
      });
      return { data: parsed, usage: turn.usage, threadId: thread.id };
    } catch (err) {
      lastErr = err;
      const classified = classifyCodexError(err);
      logToLangfuse({
        task: opts.debugTask ?? "runJsonInThread-start",
        prompt: args.start.input,
        error: classified.message,
        success: false,
      });
      logFrontendLLMDebug({
        task: opts.debugTask ?? "codex.runJsonInThread",
        mode: "start",
        threadId: thread.id,
        prompt: args.start.input,
        rawResponse,
        success: false,
        errorKind: classified.kind,
        errorMessage: classified.message,
      });
      if (classified.kind !== "generic") {
        markError(classified);
        throw classified;
      }
    }
  }
  const finalErr = classifyCodexError(lastErr);
  if (finalErr.kind !== "generic") markError(finalErr);
  throw finalErr;
}
