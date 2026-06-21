/**
 * POST /api/kg/[docId]/build — build the knowledge graph for a doc.
 *
 * Idempotent: returns the existing graph if already built. The viewer fires
 * this once at mount in parallel with per-page concept detection; the
 * server-side guard in buildKG() prevents duplicate codex calls if the user
 * reloads while a build is in flight.
 */

import { NextResponse } from "next/server";
import { buildKG } from "@/lib/kg-runner";
import { getDoc } from "@/lib/store";
import { loadKG } from "@/lib/kg";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ docId: string }> },
) {
  const { docId } = await ctx.params;
  if (!getDoc(docId)) {
    return NextResponse.json({ error: "doc not found" }, { status: 404 });
  }
  // If we already have a ready graph on disk, return it without touching codex.
  const existing = loadKG(docId);
  if (existing && existing.status === "ready") {
    return NextResponse.json(existing);
  }
  const kg = await buildKG(docId);
  return NextResponse.json(kg);
}
