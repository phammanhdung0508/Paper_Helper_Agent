import { NextResponse } from "next/server";

export const runtime = "nodejs";

const DISABLED_RESPONSE = { error: "Feynman tool is disabled" };

export async function GET() {
  return NextResponse.json(DISABLED_RESPONSE, { status: 410 });
}

export async function POST() {
  return NextResponse.json(DISABLED_RESPONSE, { status: 410 });
}

export async function DELETE() {
  return NextResponse.json(DISABLED_RESPONSE, { status: 410 });
}
