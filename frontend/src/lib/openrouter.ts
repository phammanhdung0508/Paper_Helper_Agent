import { Langfuse } from "langfuse";
import { redactSecrets } from "./llm-debug";

const CODE_VIS_MODELS = [
  "openai/gpt-oss-120b:free",
  "qwen/qwen3-coder:free",
];

const EXTRACTION_MODELS = [
  "openai/gpt-oss-120b:free",
  "qwen/qwen3-coder:free",
];

function getFamilyPrefix(modelId: string): string {
  if (modelId.includes("/")) {
    return modelId.split("/")[0];
  }
  return modelId;
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

// Log to langfuse asynchronously (fire-and-forget, non-blocking)
function logToLangfuse(args: {
  task: string;
  model: string;
  prompt: string;
  response?: string;
  success: boolean;
  error?: string;
  usage?: { promptTokens?: number; completionTokens?: number; totalTokens?: number };
}) {
  const lf = getLangfuseClient();
  if (!lf) return;
  try {
    lf.generation({
      name: `openrouter-${args.task}`,
      model: args.model,
      input: redactSecrets(args.prompt),
      output: redactSecrets(args.response || args.error),
      usage: args.usage,
      metadata: {
        provider: "openrouter",
        status: args.success ? "success" : "failed",
      },
    });
    // Do NOT await flushAsync on the critical path, just call it to schedule flush
    lf.flushAsync().catch(() => { });
  } catch (e) {
    console.warn("Failed to log OpenRouter trace to Langfuse:", e);
  }
}

export type OpenRouterResult<T> = {
  data: T;
  model: string;
  usage: unknown;
  fallbackReason?: string;
  codexFallbackUsed?: boolean;
};

export async function runOpenRouterJson<T>(
  task: string,
  prompt: string,
  outputSchema: object,
  signal?: AbortSignal,
): Promise<OpenRouterResult<T>> {
  const apiKey = process.env.OPENROUTER_API_KEY;
  const baseUrl = process.env.OPENROUTER_BASE_URL || "https://openrouter.ai/api/v1";

  if (!apiKey) {
    throw new Error("OPENROUTER_API_KEY not configured.");
  }

  // Choose the chain
  const isCode = task === "generate_visual_spec" || task.startsWith("generate_viz") || task.startsWith("repair_viz");
  const models = isCode ? CODE_VIS_MODELS : EXTRACTION_MODELS;

  const schemaInstruction = JSON.stringify(outputSchema, null, 2);
  const fullPrompt = `${prompt}\n\nReturn ONLY valid JSON matching this schema:\n${schemaInstruction}\n\nOutput ONLY the JSON object, no markdown fences, no extra text.`;

  const failedFamilies = new Set<string>();
  let lastError: Error | null = null;
  const fallbackReasons: string[] = [];

  for (const modelId of models) {
    const family = getFamilyPrefix(modelId);
    if (failedFamilies.has(family)) {
      console.log(`[OpenRouter] Skipping model '${modelId}' because family '${family}' is rate-limited.`);
      continue;
    }

    // Try twice for JSON parsing retries
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        console.log(`[OpenRouter] Calling model '${modelId}' for task '${task}' (attempt ${attempt + 1})...`);

        const response = await fetch(`${baseUrl}/chat/completions`, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${apiKey}`,
            "Content-Type": "application/json",
            "HTTP-Referer": "https://paper-helper-agent.local",
            "X-Title": "Paper Helper Agent",
          },
          body: JSON.stringify({
            model: modelId,
            messages: [
              { role: "system", content: `You are a structured JSON assistant. Task: ${task}` },
              { role: "user", content: fullPrompt }
            ],
            temperature: 0,
            response_format: { type: "json_object" }
          }),
          signal,
        });

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(`OpenRouter HTTP ${response.status}: ${errText}`);
        }

        const resData = await response.json();
        let choiceText = resData.choices?.[0]?.message?.content?.trim();
        if (!choiceText) {
          throw new Error("OpenRouter returned empty message content.");
        }

        // Clean markdown fences
        if (choiceText.startsWith("```")) {
          choiceText = choiceText
            .replace(/^```(?:json)?\s*/i, "")
            .replace(/```$/i, "")
            .trim();
        }

        let parsed: T;
        try {
          parsed = JSON.parse(choiceText) as T;
          validateSchema(parsed, outputSchema as JsonSchema);
        } catch (je: unknown) {
          if (attempt === 0) {
            continue;
          }
          const jeMsg = je instanceof Error ? je.message : String(je);
          throw new Error(`Failed to parse or validate JSON response: ${jeMsg}. Content was: ${choiceText}`);
        }

        // Log success to Langfuse
        const usageData = resData.usage ? {
          promptTokens: resData.usage.prompt_tokens,
          completionTokens: resData.usage.completion_tokens,
          totalTokens: resData.usage.total_tokens
        } : undefined;

        logToLangfuse({
          task,
          model: modelId,
          prompt: fullPrompt,
          response: choiceText,
          success: true,
          usage: usageData
        });

        return {
          data: parsed,
          model: modelId,
          usage: resData.usage,
          fallbackReason: fallbackReasons.join("; ") || undefined,
          codexFallbackUsed: false
        };

      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : String(err);
        lastError = err instanceof Error ? err : new Error(errMsg);
        const isRateLimit = errMsg.includes("429") || errMsg.toLowerCase().includes("rate limit") || errMsg.toLowerCase().includes("too many requests");

        console.warn(`[OpenRouter] Model '${modelId}' failed: ${errMsg}`);
        fallbackReasons.push(`${modelId}: ${errMsg}`);

        logToLangfuse({
          task,
          model: modelId,
          prompt: fullPrompt,
          error: errMsg,
          success: false
        });

        if (isRateLimit) {
          failedFamilies.add(family);
          break; // Break attempt loop to proceed to next model family
        }
      }
    }
  }

  throw lastError || new Error("All OpenRouter models in fallback chain failed.");
}

interface JsonSchema {
  type?: string;
  required?: string[];
  properties?: Record<string, JsonSchema>;
  additionalProperties?: boolean;
  items?: JsonSchema;
  enum?: string[];
  const?: unknown;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maxItems?: number;
}

function validateSchema(data: unknown, schema: JsonSchema, path = "root"): void {
  if (!schema) return;

  if (schema.type === "object") {
    if (typeof data !== "object" || data === null || Array.isArray(data)) {
      throw new Error(`Validation error at ${path}: expected object, got ${typeof data}`);
    }

    const obj = data as Record<string, unknown>;

    // Check required fields
    if (Array.isArray(schema.required)) {
      for (const reqKey of schema.required) {
        if (!(reqKey in obj) || obj[reqKey] === undefined) {
          throw new Error(`Validation error at ${path}: missing required property '${reqKey}'`);
        }
      }
    }

    // Check properties
    if (schema.properties) {
      for (const [key, val] of Object.entries(obj)) {
        if (schema.properties[key]) {
          validateSchema(val, schema.properties[key], `${path}.${key}`);
        } else if (schema.additionalProperties === false) {
          throw new Error(`Validation error at ${path}: additional property '${key}' not allowed`);
        }
      }
    }
  } else if (schema.type === "array") {
    if (!Array.isArray(data)) {
      throw new Error(`Validation error at ${path}: expected array, got ${typeof data}`);
    }

    if (schema.maxItems !== undefined && data.length > schema.maxItems) {
      throw new Error(`Validation error at ${path}: array length ${data.length} exceeds maxItems ${schema.maxItems}`);
    }

    if (schema.items) {
      for (let i = 0; i < data.length; i++) {
        validateSchema(data[i], schema.items, `${path}[${i}]`);
      }
    }
  } else if (schema.type === "string") {
    if (typeof data !== "string") {
      throw new Error(`Validation error at ${path}: expected string, got ${typeof data}`);
    }
    if (schema.enum && !schema.enum.includes(data)) {
      throw new Error(`Validation error at ${path}: expected one of [${schema.enum.join(", ")}], got '${data}'`);
    }
    if (schema.minLength !== undefined && data.length < schema.minLength) {
      throw new Error(`Validation error at ${path}: string length ${data.length} is less than minLength ${schema.minLength}`);
    }
    if (schema.maxLength !== undefined && data.length > schema.maxLength) {
      throw new Error(`Validation error at ${path}: string length ${data.length} exceeds maxLength ${schema.maxLength}`);
    }
  } else if (schema.type === "integer" || schema.type === "number") {
    if (typeof data !== "number") {
      throw new Error(`Validation error at ${path}: expected number, got ${typeof data}`);
    }
    if (schema.type === "integer" && !Number.isInteger(data)) {
      throw new Error(`Validation error at ${path}: expected integer, got float`);
    }
    if (schema.minimum !== undefined && data < schema.minimum) {
      throw new Error(`Validation error at ${path}: value ${data} is less than minimum ${schema.minimum}`);
    }
  } else if (schema.const !== undefined) {
    if (data !== schema.const) {
      throw new Error(`Validation error at ${path}: expected const '${schema.const}', got '${data}'`);
    }
  }
}
