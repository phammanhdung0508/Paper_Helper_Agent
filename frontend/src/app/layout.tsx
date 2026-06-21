import type { Metadata } from "next";
import "./globals.css";
import CodexHealthBanner from "@/components/CodexHealthBanner";

export const metadata: Metadata = {
  title: "Get It.",
  description:
    "Drop in any tagged PDF. Get It.'s agents pick the concepts that benefit from a picture and render them in 3D, animation, formulas, graphs, or live sources right next to the text — and back-reflect your mastery onto a knowledge graph.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className="h-full antialiased"
    >
      <body className="h-full flex flex-col overflow-hidden bg-[var(--surface-canvas)] text-[var(--ink-900)]">
        <CodexHealthBanner />
        {children}
      </body>
    </html>
  );
}
