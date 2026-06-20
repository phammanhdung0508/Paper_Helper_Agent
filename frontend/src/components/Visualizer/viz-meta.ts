import type { CSSProperties } from "react";
import { Activity, BarChart3, Box, FileText, Sigma, type LucideIcon } from "lucide-react";

import type { VizType } from "@/lib/schemas";

type VizTone = "rose" | "amber" | "emerald" | "violet" | "sky";
type VizTypeIcon = LucideIcon;
type VizTypeStyle = CSSProperties & {
  "--viz-bg": string;
  "--viz-fg": string;
  "--viz-ring": string;
};

export const VIZ_LEGEND_ORDER = [
  "3d",
  "2d-anim",
  "formula",
  "graph",
  "2d-text",
] as const satisfies readonly VizType[];

export const VIZ_TYPE_META: Record<
  VizType,
  {
    label: string;
    tone: VizTone;
    Icon: VizTypeIcon;
  }
> = {
  "3d": { label: "3D Model", tone: "rose", Icon: Box },
  "2d-anim": { label: "Animation", tone: "amber", Icon: Activity },
  "2d-text": { label: "Source", tone: "emerald", Icon: FileText },
  formula: { label: "Formula", tone: "violet", Icon: Sigma },
  graph: { label: "Graph", tone: "sky", Icon: BarChart3 },
};

const VIZ_TONE_TOKENS: Record<VizTone, { bg: string; fg: string; ring: string }> = {
  rose: {
    bg: "var(--tag-rose-bg)",
    fg: "var(--tag-rose-fg)",
    ring: "var(--tag-rose-ring)",
  },
  amber: {
    bg: "var(--tag-amber-bg)",
    fg: "var(--tag-amber-fg)",
    ring: "var(--tag-amber-ring)",
  },
  emerald: {
    bg: "var(--tag-emerald-bg)",
    fg: "var(--tag-emerald-fg)",
    ring: "var(--tag-emerald-ring)",
  },
  violet: {
    bg: "var(--tag-violet-bg)",
    fg: "var(--tag-violet-fg)",
    ring: "var(--tag-violet-ring)",
  },
  sky: {
    bg: "var(--tag-sky-bg)",
    fg: "var(--tag-sky-fg)",
    ring: "var(--tag-sky-ring)",
  },
};

export function vizTypeStyle(type: VizType): VizTypeStyle {
  const tokens = VIZ_TONE_TOKENS[VIZ_TYPE_META[type].tone];
  return {
    "--viz-bg": tokens.bg,
    "--viz-fg": tokens.fg,
    "--viz-ring": tokens.ring,
  };
}
