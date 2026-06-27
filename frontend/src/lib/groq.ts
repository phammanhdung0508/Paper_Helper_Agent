import { Langfuse } from "langfuse";
import { redactSecrets } from "./llm-debug";
import { serverEnv } from "./server-env";

const GENERAL_MODELS = [
  "llama-3.1-8b-instant",
  "groq/compound-mini",
];

const EXTRACTION_MODELS = [
  "llama-3.1-8b-instant",
  "groq/compound-mini",
];

const CODE_VIS_MODELS = [
  "qwen/qwen3-32b",
  "qwen/qwen3.6-27b",
];

const EVAL_MODELS = [
  "llama-3.1-8b-instant",
  "groq/compound-mini",
];

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
      name: `groq-${args.task}`,
      model: args.model,
      input: redactSecrets(args.prompt),
      output: redactSecrets(args.response || args.error),
      usage: args.usage,
      metadata: {
        provider: "groq",
        status: args.success ? "success" : "failed",
      },
    });
    lf.flushAsync().catch(() => { });
  } catch (e) {
    console.warn("Failed to log Groq trace to Langfuse:", e);
  }
}

export type GroqResult<T> = {
  data: T;
  model: string;
  usage: unknown;
  fallbackReason?: string;
};

export async function runGroqJson<T>(
  task: string,
  prompt: string,
  outputSchema: object,
  signal?: AbortSignal,
): Promise<GroqResult<T>> {
  const apiKey = serverEnv("GROQ_API_KEY");
  const baseUrl = serverEnv("GROQ_BASE_URL") || "https://api.groq.com/openai/v1";

  if (!apiKey) {
    throw new Error("GROQ_API_KEY not configured.");
  }

  const models = modelsForTask(task);
  const customModel = serverEnv("GROQ_MODEL");
  if (customModel && !models.includes(customModel)) {
    models.unshift(customModel);
  }

  const schemaInstruction = JSON.stringify(outputSchema, null, 2);
  const fullPrompt = `${prompt}\n\nReturn ONLY valid JSON matching this schema:\n${schemaInstruction}\n\nOutput ONLY the JSON object, no markdown fences, no extra text.`;

  let lastError: Error | null = null;
  const fallbackReasons: string[] = [];

  for (const modelId of models) {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        console.log(`[Groq] Calling model '${modelId}' for task '${task}' (attempt ${attempt + 1})...`);

        const response = await fetch(`${baseUrl}/chat/completions`, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${apiKey}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            model: modelId,
            messages: [
              { role: "system", content: `You are a structured JSON assistant. Task: ${task}` },
              { role: "user", content: fullPrompt },
            ],
            temperature: 0,
            max_tokens: 2048,
          }),
          signal,
        });

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(`Groq HTTP ${response.status}: ${errText}`);
        }

        const resData = await response.json();
        let choiceText = resData.choices?.[0]?.message?.content?.trim();
        if (!choiceText) {
          throw new Error("Groq returned empty message content.");
        }

        if (choiceText.startsWith("```")) {
          choiceText = choiceText
            .replace(/^```(?:json)?\s*/i, "")
            .replace(/```$/i, "")
            .trim();
        }
        choiceText = extractJsonObject(choiceText);

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

        const usageData = resData.usage ? {
          promptTokens: resData.usage.prompt_tokens,
          completionTokens: resData.usage.completion_tokens,
          totalTokens: resData.usage.total_tokens,
        } : undefined;

        logToLangfuse({
          task,
          model: modelId,
          prompt: fullPrompt,
          response: choiceText,
          success: true,
          usage: usageData,
        });

        return {
          data: parsed,
          model: modelId,
          usage: resData.usage,
          fallbackReason: fallbackReasons.join("; ") || undefined,
        };
      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : String(err);
        lastError = err instanceof Error ? err : new Error(errMsg);
        console.warn(`[Groq] Model '${modelId}' failed: ${errMsg}`);
        fallbackReasons.push(`${modelId}: ${errMsg}`);
        logToLangfuse({
          task,
          model: modelId,
          prompt: fullPrompt,
          error: errMsg,
          success: false,
        });
        if (isAuthError(errMsg)) {
          throw lastError;
        }
        if (isRateLimit(errMsg)) {
          break;
        }
      }
    }
  }

  throw lastError || new Error("All Groq models in fallback chain failed.");
}

function modelsForTask(task: string): string[] {
  if (task === "generate_visual_spec" || task.startsWith("generate_viz") || task.startsWith("repair_viz")) {
    return [...CODE_VIS_MODELS];
  }
  if (task === "evaluate_mastery_response" || task.includes("evaluate")) {
    return [...EVAL_MODELS];
  }
  if (task === "extract_knowledge_graph" || task === "concept_detection" || task.includes("extract") || task.includes("detect")) {
    return [...EXTRACTION_MODELS];
  }
  return [...GENERAL_MODELS];
}

function isRateLimit(message: string): boolean {
  const lower = message.toLowerCase();
  return message.includes("429") || lower.includes("rate limit") || lower.includes("too many requests");
}

function isAuthError(message: string): boolean {
  const lower = message.toLowerCase();
  return message.includes("401") || message.includes("403") || lower.includes("api key") || lower.includes("auth");
}

function extractJsonObject(text: string): string {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end === -1 || end < start) return text;
  return text.slice(start, end + 1);
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
    if (Array.isArray(schema.required)) {
      for (const reqKey of schema.required) {
        if (!(reqKey in obj) || obj[reqKey] === undefined) {
          throw new Error(`Validation error at ${path}: missing required property '${reqKey}'`);
        }
      }
    }
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
  } else if (schema.const !== undefined && data !== schema.const) {
    throw new Error(`Validation error at ${path}: expected const '${schema.const}', got '${data}'`);
  }
}
