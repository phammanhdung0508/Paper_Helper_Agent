"use client";

/**
 * Small wrapper that gives a tab-bar button the same custom tooltip that
 * PDF concept tags already use. Reuses the existing .viz-tooltip /
 * .viz-tooltip-anchor classes from app/globals.css so the hover styling
 * (white rounded card, soft shadow, fast fade-in) is shared across the
 * whole app.
 *
 * Why a wrapper instead of native `title=""`: native tooltips have a
 * ~700 ms delay and inherit OS styling; the in-app pattern matches the
 * rest of the UI and renders instantly. We still set `aria-label` on
 * the inner button (where the caller does) so screen readers don't lose
 * the cue.
 */

import type { ReactNode } from "react";

export default function TooltipChip({
  tip,
  children,
  className = "",
}: {
  tip: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={`viz-tooltip-anchor relative inline-flex ${className}`}>
      {children}
      <span className="viz-tooltip" role="tooltip">
        {tip}
      </span>
    </span>
  );
}
