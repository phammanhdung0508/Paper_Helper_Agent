import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import { pdfPath, getDoc } from "@/lib/store";

export const runtime = "nodejs";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ docId: string }> },
) {
  const { docId } = await ctx.params;
  const doc = getDoc(docId);
  if (!doc) return NextResponse.json({ error: "not found" }, { status: 404 });
  const buf = await fs.readFile(pdfPath(docId));
  return new NextResponse(buf, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Length": String(buf.length),
      "Cache-Control": "private, max-age=600",
    },
  });
}
