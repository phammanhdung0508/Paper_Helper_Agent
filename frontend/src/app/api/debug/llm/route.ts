import { NextResponse } from "next/server";
import { isLLMDebugEnabled, readLLMDebugEntries } from "@/lib/llm-debug";

export const runtime = "nodejs";

export async function GET(req: Request) {
  if (!isLLMDebugEnabled()) {
    return NextResponse.json({ error: "LLM debug logging is disabled" }, { status: 404 });
  }
  const url = new URL(req.url);
  const limit = Math.min(500, Math.max(1, Number(url.searchParams.get("limit") ?? 100)));
  const task = url.searchParams.get("task");
  const success = url.searchParams.get("success");
  let entries = readLLMDebugEntries(limit);
  if (task) entries = entries.filter((entry) => entry.task.includes(task));
  if (success === "true") entries = entries.filter((entry) => entry.success);
  if (success === "false") entries = entries.filter((entry) => !entry.success);
  return NextResponse.json({ entries });
}
