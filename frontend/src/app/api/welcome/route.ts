/**
 * GET  /api/welcome    → { dismissedVersion, currentVersion, shouldShow }
 * POST /api/welcome    → marks the welcome popup as dismissed for the
 *                        current app version. After this the popup
 *                        won't reappear until the user updates to a
 *                        newer version of Get It.
 *
 * The dismissed-version flag lives at <DATA_DIR>/welcome.json. We
 * compare against the build-time-baked APP_VERSION; any mismatch
 * (first run, post-update) flips shouldShow back to true.
 */

import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";
import { DATA_DIR } from "@/lib/paths";
import { APP_VERSION } from "@/lib/version";

export const runtime = "nodejs";

const WELCOME_PATH = path.join(DATA_DIR, "welcome.json");

function readDismissed(): string | null {
  try {
    const raw = fs.readFileSync(WELCOME_PATH, "utf-8");
    const parsed = JSON.parse(raw) as { dismissedVersion?: string };
    return typeof parsed.dismissedVersion === "string"
      ? parsed.dismissedVersion
      : null;
  } catch {
    return null;
  }
}

function writeDismissed(version: string): void {
  const tmp = `${WELCOME_PATH}.tmp`;
  fs.writeFileSync(
    tmp,
    JSON.stringify({ dismissedVersion: version, savedAt: Date.now() }, null, 2),
  );
  fs.renameSync(tmp, WELCOME_PATH);
}

export async function GET() {
  const dismissedVersion = readDismissed();
  return NextResponse.json({
    dismissedVersion,
    currentVersion: APP_VERSION,
    shouldShow: dismissedVersion !== APP_VERSION,
  });
}

export async function POST() {
  writeDismissed(APP_VERSION);
  return NextResponse.json({ ok: true, dismissedVersion: APP_VERSION });
}
