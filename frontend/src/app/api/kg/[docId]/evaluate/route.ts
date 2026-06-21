/**
 * POST /api/kg/[docId]/evaluate — request a fresh evaluation pass.
 *
 * Tools call this implicitly after appending to the work context, but the
 * route is also exposed so the client (or a developer) can manually trigger
 * a re-score. Returns immediately — work happens in the per-doc queue.
 */

import { NextResponse } from "next/server";
import { scheduleEvaluation } from "@/lib/kg-runner";
import { getDoc } from "@/lib/store";

export const runtime = "nodejs";

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ docId: string }> },
) {
  const { docId } = await ctx.params;
  if (!getDoc(docId)) {
    return NextResponse.json({ error: "doc not found" }, { status: 404 });
  }
  scheduleEvaluation(docId);
  return NextResponse.json({ ok: true });
}
