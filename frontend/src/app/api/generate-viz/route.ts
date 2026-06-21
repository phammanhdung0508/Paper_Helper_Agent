/**
 * POST /api/generate-viz
 *
 *   { type, label, context, docTitle?, previousAttempt? }
 *
 * Returns: VizSpec (object matching the type's schema).
 *
 * Legacy route — kept for back-compat with older clients. The
 * packaged Electron app routes per-tag generation through the
 * server-side viz queue (see lib/jobs.ts → requestVizGeneration).
 */

import { NextResponse } from "next/server";
import { generateVizSpec } from "@/lib/agents/viz";
import { VIZ_TYPES, type VizSpec, type VizType } from "@/lib/schemas";

export const runtime = "nodejs";
export const maxDuration = 180;

export async function POST(req: Request) {
  const body = (await req.json()) as {
    type?: VizType;
    label?: string;
    context?: string;
    docTitle?: string;
    previousAttempt?: { spec: VizSpec; runtimeError: string };
  };
  if (!body.type || !VIZ_TYPES.includes(body.type)) {
    return NextResponse.json({ error: "invalid type" }, { status: 400 });
  }
  if (!body.label || !body.context) {
    return NextResponse.json({ error: "label and context required" }, { status: 400 });
  }
  const spec = await generateVizSpec({
    type: body.type,
    label: body.label,
    context: body.context,
    docTitle: body.docTitle,
    previousAttempt: body.previousAttempt,
  });
  return NextResponse.json(spec);
}
