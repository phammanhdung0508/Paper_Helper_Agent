/**
 * POST /api/analyze-pdf
 *   { docId, pageIndex }
 *
 * Returns: { concepts: DetectedConcept[], anchors: { id: { endX, endY, fontHeight } | null } }
 *
 * Legacy route — preserved for the older client orchestration tests
 * under scripts/. The packaged Electron app drives detection via the
 * server-side `ensureDetection` job (see lib/jobs.ts) which persists
 * tags as it goes; this route still works but isn't on the hot path.
 */

import { NextResponse } from "next/server";
import { detectConceptsForPage } from "@/lib/agents/detect";
import { getDoc } from "@/lib/store";
import { locateAnchor } from "@/lib/pdf-extract";

export const runtime = "nodejs";
export const maxDuration = 120;

export async function POST(req: Request) {
  const body = (await req.json()) as { docId?: string; pageIndex?: number };
  const docId = body.docId;
  const pageIndex = body.pageIndex;
  if (!docId || pageIndex == null) {
    return NextResponse.json({ error: "docId and pageIndex required" }, { status: 400 });
  }
  const doc = getDoc(docId);
  if (!doc) return NextResponse.json({ error: "doc not found" }, { status: 404 });
  const page = doc.extracted.pages[pageIndex];
  if (!page) return NextResponse.json({ error: "page out of range" }, { status: 400 });

  if (page.text.length < 120) {
    return NextResponse.json({ concepts: [], anchors: {} });
  }

  const { concepts } = await detectConceptsForPage(pageIndex, page.text);

  const anchors: Record<number, { endX: number; endY: number; fontHeight: number } | null> = {};
  concepts.forEach((c, idx) => {
    anchors[idx] = locateAnchor(page, c.anchor);
  });

  return NextResponse.json({
    concepts,
    anchors,
    pageWidth: page.width,
    pageHeight: page.height,
  });
}
