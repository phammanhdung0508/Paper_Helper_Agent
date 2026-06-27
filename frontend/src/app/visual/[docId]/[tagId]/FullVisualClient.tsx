"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { VizSpec } from "@/lib/schemas";
import ThreeDView from "@/components/Visualizer/ThreeDView";
import TwoDAnimView from "@/components/Visualizer/TwoDAnimView";
import TwoDTextView from "@/components/Visualizer/TwoDTextView";
import FormulaView from "@/components/Visualizer/FormulaView";
import GraphView from "@/components/Visualizer/GraphView";
import { VIZ_TYPE_META, vizTypeStyle } from "@/components/Visualizer/viz-meta";

type Props = {
  docId: string;
  tagId: string;
  label: string;
  spec: VizSpec;
};

export default function FullVisualClient({ docId, tagId, label, spec }: Props) {
  const Icon = VIZ_TYPE_META[spec.type].Icon;
  return (
    <main className="flex min-h-screen flex-col bg-[var(--surface-canvas)]">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--border-subtle)] bg-white px-5 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href={`/viewer/${docId}`}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border-subtle)] text-[var(--ink-600)] hover:bg-[var(--surface-sunken)]"
            aria-label="Back to viewer"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <span className="viz-type-chip" style={vizTypeStyle(spec.type)}>
            <Icon className="h-3 w-3" aria-hidden />
            {VIZ_TYPE_META[spec.type].label}
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold text-[var(--ink-900)]">{spec.title}</h1>
            <p className="truncate text-xs text-[var(--ink-500)]">{label}</p>
          </div>
        </div>
        <span className="hidden text-[11px] text-[var(--ink-400)] sm:inline">{tagId}</span>
      </header>

      <section className="min-h-0 flex-1 overflow-auto p-4">
        <div className="mx-auto h-[calc(100vh-9.5rem)] min-h-[640px] w-full min-w-[960px] max-w-[1280px] overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-white shadow-[0_8px_30px_rgba(17,17,19,0.06)]">
          {spec.type === "3d" && <ThreeDView spec={spec} />}
          {spec.type === "2d-anim" && <TwoDAnimView spec={spec} />}
          {spec.type === "2d-text" && <TwoDTextView spec={spec} />}
          {spec.type === "formula" && <FormulaView spec={spec} />}
          {spec.type === "graph" && <GraphView spec={spec} />}
        </div>
      </section>

      <footer className="shrink-0 border-t border-[var(--border-subtle)] bg-white px-5 py-3">
        <p className="mx-auto max-w-[1280px] text-[12.5px] leading-relaxed text-[var(--ink-700)]">{spec.caption}</p>
      </footer>
    </main>
  );
}
