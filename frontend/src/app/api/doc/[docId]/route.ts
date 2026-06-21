import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import { getDoc, pdfPath, saveDoc } from "@/lib/store";
import { extractPdf } from "@/lib/pdf-extract";

export const runtime = "nodejs";

function hasExtractedText(doc: NonNullable<ReturnType<typeof getDoc>>): boolean {
  return doc.extracted.pages.some((page) => page.text.trim().length >= 120);
}

async function repairEmptyExtraction(doc: NonNullable<ReturnType<typeof getDoc>>) {
  if (hasExtractedText(doc)) return doc;
  const buffer = await fs.readFile(pdfPath(doc.id));
  const u8 = new Uint8Array(buffer.byteLength);
  u8.set(buffer);
  const extracted = await extractPdf(u8);
  if (!extracted.pages.some((page) => page.text.trim().length >= 120)) return doc;
  const repaired = { ...doc, numPages: extracted.numPages, extracted };
  saveDoc(repaired);
  return repaired;
}

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ docId: string }> },
) {
  const { docId } = await ctx.params;
  let doc = getDoc(docId);
  if (!doc) return NextResponse.json({ error: "not found" }, { status: 404 });
  try {
    doc = await repairEmptyExtraction(doc);
  } catch (e) {
    console.warn("[doc-repair-extraction]", docId, e instanceof Error ? e.message : e);
  }
  return NextResponse.json({
    docId: doc.id,
    filename: doc.filename,
    pdfUrl: doc.pdfUrl,
    numPages: doc.extracted.numPages,
    pages: doc.extracted.pages.map((p) => ({
      pageIndex: p.pageIndex,
      width: p.width,
      height: p.height,
      text: p.text,
    })),
  });
}
