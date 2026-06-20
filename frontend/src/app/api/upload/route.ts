/**
 * POST /api/upload
 *   multipart/form-data:
 *     - file: <PDF blob>      (when uploading from the user's machine)
 *     - sample: <name>        (when picking one of /public/pdfs/<name>.pdf)
 *
 * Returns: { docId, numPages, pages: [{ pageIndex, width, height, text }], pdfUrl }
 *
 * Sample idempotency: clicking the same sample twice returns the same
 * docId so the user's KG / chats / flashcards / quizzes / feynman sessions
 * survive a back-and-forth.
 * Real uploads always mint a new docId — students who genuinely re-upload
 * the same file get a new entry and can delete duplicates from Library.
 */

import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";
import {
  extractPdf,
  assessPdfQuality,
  PdfUnsupportedError,
  MAX_PDF_PAGES,
  type ExtractedPdf,
  type PdfRejectReason,
  type PdfQualityStats,
} from "@/lib/pdf-extract";
import { ensureDocDir, pdfPath } from "@/lib/paths";
import { getDoc, newDocId, saveDoc } from "@/lib/store";

export const runtime = "nodejs";
export const maxDuration = 60;

const SAMPLE_NAME_TO_DOC_ID: Record<string, string> = {
  anatomy: "sample-anatomy",
  physics: "sample-physics",
  costituzione: "sample-costituzione",
  calculus: "sample-calculus",
  chemistry: "sample-chemistry",
};

/** User-facing copy for every rejection/warning reason. Coherent voice across
 *  the whole gate so the UploadCard alert reads the same regardless of cause. */
function rejectionMessage(reason: PdfRejectReason, stats?: PdfQualityStats): string {
  switch (reason) {
    case "too_many_pages":
      return `This document has ${stats?.numPages ?? "too many"} pages. Get It. supports PDFs up to ${MAX_PDF_PAGES} pages — try a single chapter or a shorter export.`;
    case "no_text":
      return "This PDF has almost no selectable text. Get It. reads the text layer of a document, not pictures of pages — this looks like a scan or an image-only export. Try a digital, text-based PDF (one where you can select the text in a reader).";
    case "image_dominant":
      return `This looks like a scanned or image-heavy PDF — only ${stats?.textPages ?? 0} of ${stats?.numPages ?? 0} pages have a usable text layer. Get It. reads text, not images, so too much of this document would be lost. Try a digital, text-based PDF.`;
    case "unreadable":
    default:
      return "This PDF couldn't be read — it may be encrypted, password-protected, or corrupted. Try re-exporting it or removing protection, then upload again.";
  }
}

function warningMessage(reason: PdfRejectReason, stats?: PdfQualityStats): string {
  switch (reason) {
    case "no_text":
      return "This PDF has very little selectable text. It was uploaded, but chat, concept detection, and study tools may be limited unless OCR is added.";
    case "image_dominant":
      return `This PDF looks image-heavy — only ${stats?.textPages ?? 0} of ${stats?.numPages ?? 0} pages have a usable text layer. You can view it, but AI study features may be limited.`;
    default:
      return rejectionMessage(reason, stats);
  }
}

function rejectResponse(reason: PdfRejectReason, stats?: PdfQualityStats) {
  return NextResponse.json(
    { error: rejectionMessage(reason, stats), code: reason, stats },
    { status: 422 },
  );
}

function fallbackExtractedPdf(buffer: Buffer): ExtractedPdf | null {
  const latin = buffer.toString("latin1");
  if (latin.includes("/Encrypt")) return null;
  const matches = latin.match(/\/Type\s*\/Page\b/g);
  const numPages = matches?.length ?? 0;
  if (numPages <= 0 || numPages > MAX_PDF_PAGES) return null;
  return {
    numPages,
    pages: Array.from({ length: numPages }, (_, index) => ({
      pageIndex: index,
      width: 595,
      height: 842,
      items: [],
      text: "",
    })),
  };
}

export async function POST(req: Request) {
  let buffer: Buffer;
  let filename = "uploaded.pdf";
  let presetDocId: string | null = null;
  let qualityWarning: { code: PdfRejectReason; message: string; stats?: PdfQualityStats } | null = null;

  const ct = req.headers.get("content-type") || "";
  if (ct.includes("multipart/form-data")) {
    const form = await req.formData();
    const sample = form.get("sample");
    if (typeof sample === "string" && sample) {
      const safe = sample.replace(/[^a-z0-9-]/gi, "");
      const sampleDocId = SAMPLE_NAME_TO_DOC_ID[safe];
      if (!sampleDocId) {
        return NextResponse.json({ error: "unknown sample" }, { status: 400 });
      }
      // Already in the library? Reuse it.
      const existing = getDoc(sampleDocId);
      if (existing) {
        return NextResponse.json({
          docId: existing.id,
          filename: existing.filename,
          pdfUrl: existing.pdfUrl,
          numPages: existing.extracted.numPages,
          pages: existing.extracted.pages.map((p) => ({
            pageIndex: p.pageIndex,
            width: p.width,
            height: p.height,
            text: p.text,
          })),
        });
      }
      const p = path.join(process.cwd(), "public", "pdfs", `${safe}.pdf`);
      buffer = await fs.readFile(p);
      filename = `${safe}.pdf`;
      presetDocId = sampleDocId;
    } else {
      const file = form.get("file");
      if (!(file instanceof Blob)) {
        return NextResponse.json({ error: "no file" }, { status: 400 });
      }
      buffer = Buffer.from(await file.arrayBuffer());
      const fname = (file as unknown as { name?: string }).name;
      if (fname) filename = fname.replace(/[^a-z0-9._-]/gi, "_");
    }
  } else {
    return NextResponse.json({ error: "expected multipart/form-data" }, { status: 400 });
  }

  // Sanity: must look like a PDF.
  if (buffer.subarray(0, 5).toString("ascii") !== "%PDF-") {
    return NextResponse.json({ error: "not a PDF" }, { status: 400 });
  }

  // Extract FIRST, from the in-memory bytes, so we can gate the document
  // before writing anything to disk or kicking off any agent workflow. A
  // rejected upload leaves no orphan files behind.
  //
  // pdf.js refuses Buffer instances; copy to a plain Uint8Array.
  const u8 = new Uint8Array(buffer.byteLength);
  u8.set(buffer);
  let extracted: ExtractedPdf;
  try {
    extracted = await extractPdf(u8);
  } catch (e) {
    if (e instanceof PdfUnsupportedError) {
      return rejectResponse(e.reason, e.stats);
    }
    const fallback = fallbackExtractedPdf(buffer);
    if (!fallback) {
      // pdf.js throws on encrypted / corrupt files — surface a friendly hint
      // instead of a 500.
      return rejectResponse("unreadable");
    }
    extracted = fallback;
    qualityWarning = {
      code: "no_text",
      message:
        "This PDF was uploaded in viewer-only mode because its text layer could not be extracted. You can view it, but AI study features may be limited unless OCR is added.",
      stats: {
        numPages: fallback.numPages,
        textPages: 0,
        totalAlnum: 0,
        richRatio: 0,
      },
    };
  }

  // Text-coverage gate. For this project, low-text / image-heavy PDFs are
  // still useful as viewable report/demo artifacts, so we warn instead of
  // rejecting. Hard limits like too_many_pages and unreadable PDFs still fail.
  if (!presetDocId) {
    const quality = assessPdfQuality(extracted);
    if (!quality.ok) {
      const reason = quality.reason as PdfRejectReason;
      if (reason === "no_text" || reason === "image_dominant") {
        qualityWarning = {
          code: reason,
          message: warningMessage(reason, quality.stats),
          stats: quality.stats,
        };
      } else {
        return rejectResponse(reason, quality.stats);
      }
    }
  }

  const docId = presetDocId ?? newDocId();
  ensureDocDir(docId);
  await fs.writeFile(pdfPath(docId), buffer);
  const pdfUrl = `/api/pdf/${docId}`;

  saveDoc({
    id: docId,
    filename,
    uploadedAt: Date.now(),
    numPages: extracted.numPages,
    extracted,
    pdfUrl,
  });

  return NextResponse.json({
    docId,
    filename,
    pdfUrl,
    numPages: extracted.numPages,
    pages: extracted.pages.map((p) => ({
      pageIndex: p.pageIndex,
      width: p.width,
      height: p.height,
      text: p.text,
    })),
    warning: qualityWarning,
  });
}
