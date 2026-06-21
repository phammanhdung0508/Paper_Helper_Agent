/**
 * POST /api/doc/[docId]/touch
 *
 * Bumps the doc's `lastOpenedAt` timestamp. The viewer pings this on
 * mount so the Library row's "last opened" reflects real opens, not
 * just side effects (KG evals, chat writes, etc.).
 */

import { NextResponse } from "next/server";
import { getDoc, touchDoc } from "@/lib/store";

export const runtime = "nodejs";

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ docId: string }> },
) {
  const { docId } = await ctx.params;
  if (!getDoc(docId)) {
    return NextResponse.json({ error: "doc not found" }, { status: 404 });
  }
  const next = touchDoc(docId);
  return NextResponse.json({ ok: true, lastOpenedAt: next?.lastOpenedAt ?? null });
}
