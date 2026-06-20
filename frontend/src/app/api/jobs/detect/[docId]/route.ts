/**
 * POST /api/jobs/detect/[docId]
 *
 * Idempotent: starts the server-side concept-detection job for a doc
 * if one isn't already running. Returns immediately — the viewer polls
 * /api/tags/<docId> for progress (pagesAnalyzed grows, tags append).
 */

import { NextResponse } from "next/server";
import { getDoc } from "@/lib/store";
import { ensureDetection, isDetectionRunning } from "@/lib/jobs";

export const runtime = "nodejs";

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ docId: string }> },
) {
  const { docId } = await ctx.params;
  if (!getDoc(docId)) {
    return NextResponse.json({ error: "doc not found" }, { status: 404 });
  }
  ensureDetection(docId);
  return NextResponse.json({ ok: true, running: isDetectionRunning(docId) });
}
