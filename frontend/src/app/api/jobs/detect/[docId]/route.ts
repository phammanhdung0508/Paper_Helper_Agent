/**
 * POST /api/jobs/detect/[docId]
 *
 * Idempotent: starts the server-side concept-detection job for a doc
 * if one isn't already running. Returns immediately — the viewer polls
 * /api/tags/<docId> for progress (pagesAnalyzed grows, tags append).
 */

import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import { getDoc, pdfPath, saveDoc } from "@/lib/store";
import { ensureDetection, isDetectionRunning } from "@/lib/jobs";
import { extractPdf } from "@/lib/pdf-extract";
import { loadTags, saveTags } from "@/lib/tags-store";

export const runtime = "nodejs";

function hasExtractedText(doc: NonNullable<ReturnType<typeof getDoc>>): boolean {
  return doc.extracted.pages.some((page) => page.text.trim().length >= 120);
}

async function refreshEmptyExtraction(doc: NonNullable<ReturnType<typeof getDoc>>) {
  if (hasExtractedText(doc)) return;
  const buffer = await fs.readFile(pdfPath(doc.id));
  const u8 = new Uint8Array(buffer.byteLength);
  u8.set(buffer);
  const extracted = await extractPdf(u8);
  if (!extracted.pages.some((page) => page.text.trim().length >= 120)) return;
  saveDoc({
    ...doc,
    numPages: extracted.numPages,
    extracted,
  });
  const tags = loadTags(doc.id);
  if (tags && tags.tags.length === 0 && tags.pagesAnalyzed.length > 0) {
    saveTags(doc.id, { tags: [], activeTagId: null, pagesAnalyzed: [] });
  }
}

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ docId: string }> },
) {
  const { docId } = await ctx.params;
  const doc = getDoc(docId);
  if (!doc) {
    return NextResponse.json({ error: "doc not found" }, { status: 404 });
  }
  try {
    await refreshEmptyExtraction(doc);
  } catch (e) {
    console.warn("[jobs/detect-refresh]", docId, e instanceof Error ? e.message : e);
  }
  ensureDetection(docId);
  return NextResponse.json({ ok: true, running: isDetectionRunning(docId) });
}
