import Link from "next/link";
import { isLLMDebugEnabled, LLM_DEBUG_LOG_PATH, readLLMDebugEntries } from "@/lib/llm-debug";

export const dynamic = "force-dynamic";

function preview(value?: string, length = 180): string {
  if (!value) return "";
  const flat = value.replace(/\s+/g, " ").trim();
  return flat.length > length ? `${flat.slice(0, length)}...` : flat;
}

export default function LLMDebugPage() {
  const enabled = isLLMDebugEnabled();
  const entries = enabled ? readLLMDebugEntries(100) : [];

  return (
    <main className="min-h-screen bg-white px-6 py-6 text-[var(--ink-900)]">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">LLM Debug Log</h1>
          <p className="mt-1 text-sm text-[var(--ink-500)]">
            Raw Codex responses before parsing. Enable with <code>DEBUG_LLM_RESPONSES=1</code>.
          </p>
        </div>
        <Link href="/" className="rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-sm hover:bg-[var(--surface-sunken)]">
          Home
        </Link>
      </div>

      {!enabled && (
        <section className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Debug logging is disabled. Start the frontend with <code>DEBUG_LLM_RESPONSES=1</code> to collect and view entries.
        </section>
      )}

      {enabled && (
        <>
          <p className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-3 py-2 text-xs text-[var(--ink-500)]">
            Log file: <code>{LLM_DEBUG_LOG_PATH}</code>
          </p>
          <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
            <table className="w-full border-collapse text-left text-xs">
              <thead className="bg-[var(--surface-canvas)] text-[var(--ink-500)]">
                <tr>
                  <th className="px-3 py-2 font-medium">Time</th>
                  <th className="px-3 py-2 font-medium">Task</th>
                  <th className="px-3 py-2 font-medium">Mode</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Prompt</th>
                  <th className="px-3 py-2 font-medium">Raw Response</th>
                </tr>
              </thead>
              <tbody>
                {entries.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-[var(--ink-400)]">
                      No debug entries yet.
                    </td>
                  </tr>
                )}
                {entries.map((entry) => (
                  <tr key={entry.id} className="border-t border-[var(--border-subtle)] align-top">
                    <td className="whitespace-nowrap px-3 py-2 text-[var(--ink-500)]">
                      {new Date(entry.createdAt).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 font-medium">{entry.task}</td>
                    <td className="px-3 py-2 text-[var(--ink-500)]">{entry.mode ?? "-"}</td>
                    <td className="px-3 py-2">
                      <span className={entry.success ? "text-emerald-700" : "text-rose-700"}>
                        {entry.success ? "success" : entry.errorKind ?? "failed"}
                      </span>
                    </td>
                    <td className="max-w-md px-3 py-2 text-[var(--ink-600)]">{preview(entry.prompt)}</td>
                    <td className="max-w-md px-3 py-2 text-[var(--ink-600)]">{preview(entry.rawResponse || entry.errorMessage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}
