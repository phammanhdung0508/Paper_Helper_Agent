import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

export const runtime = "nodejs";

const SAMPLES = [
  { id: "anatomy", title: "Human Anatomy & Physiology", description: "Heart, pancreas, brain — perfect for 3D anatomy renders.", color: "from-rose-400 to-pink-600" },
  { id: "physics", title: "Classical Mechanics", description: "Inclined planes, pendulums, projectiles — animated 2D simulations.", color: "from-amber-300 to-orange-500" },
  { id: "costituzione", title: "Costituzione Italiana", description: "Articoli e sentenze costituzionali — fonti citate e linkate.", color: "from-emerald-400 to-teal-600" },
  { id: "calculus", title: "Differential & Integral Calculus", description: "Derivatives, integrals, Taylor series — formulas + graphs.", color: "from-violet-400 to-indigo-600" },
  { id: "chemistry", title: "Organic Chemistry", description: "Methane, water, benzene — molecular 3D models.", color: "from-sky-400 to-cyan-600" },
];

export async function GET() {
  const dir = path.join(process.cwd(), "public", "pdfs");
  const out = [] as Array<typeof SAMPLES[number] & { sizeKb: number }>;
  for (const s of SAMPLES) {
    try {
      const stat = await fs.stat(path.join(dir, `${s.id}.pdf`));
      out.push({ ...s, sizeKb: Math.round(stat.size / 1024) });
    } catch {
      // skip missing
    }
  }
  return NextResponse.json({ samples: out });
}
