"use client";

/**
 * Chat with the document.
 *
 * Sidebar: list of chats (most-recent first), "+ new" button. Main: open
 * thread with a tight ChatGPT-style input and tap-and-go shipping. We never
 * cap the visible history because chats are scoped per-doc and the codex
 * model receives a server-side excerpt.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Trash2, Send, MessageSquare, RefreshCw } from "lucide-react";
import type { ChatThread } from "@/lib/work-context-types";
import { consumePrefill } from "./prefill";

type Props = { docId: string };

export default function ChatView({ docId }: Props) {
  const [chats, setChats] = useState<ChatThread[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);

  // Initial fetch + handle prefill from a "Chat about this concept" jump
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/chat/${docId}`)
      .then((r) => r.json())
      .then(async (j: { chats: ChatThread[] }) => {
        if (cancelled) return;
        setChats(j.chats);
        // One-shot prefill from a knowledge-graph jump.
        const prefill = consumePrefill(docId, "chat");
        if (prefill) {
          // Create a fresh chat for this concept and seed the draft.
          const r = await fetch(`/api/chat/${docId}`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ action: "create", title: prefill }),
          });
          const { chat } = (await r.json()) as { chat: ChatThread };
          if (cancelled) return;
          setChats((prev) => [chat, ...(prev ?? j.chats)]);
          setActiveId(chat.id);
          setDraft(`Spiegami "${prefill}".`);
          return;
        }
        if (j.chats.length && !activeId) setActiveId(j.chats[0].id);
      })
      .catch(() => {
        if (!cancelled) setChats([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  const active = useMemo(
    () => chats?.find((c) => c.id === activeId) ?? null,
    [chats, activeId],
  );

  // Auto-scroll to the bottom when messages change.
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [active?.messages.length, sending]);

  const createChat = useCallback(async () => {
    setCreating(true);
    try {
      const r = await fetch(`/api/chat/${docId}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "create" }),
      });
      const j = (await r.json()) as { chat: ChatThread };
      setChats((prev) => [j.chat, ...(prev ?? [])]);
      setActiveId(j.chat.id);
    } finally {
      setCreating(false);
    }
  }, [docId]);

  const deleteChat = useCallback(
    async (id: string) => {
      await fetch(`/api/chat/${docId}?chatId=${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      setChats((prev) => (prev ? prev.filter((c) => c.id !== id) : prev));
      if (activeId === id) setActiveId(null);
    },
    [docId, activeId],
  );

  const send = useCallback(async () => {
    const message = draft.trim();
    if (!message || sending) return;
    let chatId = activeId;
    if (!chatId) {
      // Auto-create a chat on first send.
      const r = await fetch(`/api/chat/${docId}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "create" }),
      });
      const j = (await r.json()) as { chat: ChatThread };
      chatId = j.chat.id;
      setChats((prev) => [j.chat, ...(prev ?? [])]);
      setActiveId(j.chat.id);
    }
    // Optimistic: append the user message immediately.
    const optimisticUser = {
      role: "user" as const,
      content: message,
      ts: Date.now(),
    };
    setChats((prev) =>
      prev
        ? prev.map((c) =>
            c.id === chatId
              ? { ...c, messages: [...c.messages, optimisticUser], updatedAt: optimisticUser.ts }
              : c,
          )
        : prev,
    );
    setDraft("");
    setSending(true);
    try {
      const r = await fetch(`/api/chat/${docId}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "send", chatId, message }),
      });
      if (!r.ok) throw new Error(`send failed (${r.status})`);
      const j = (await r.json()) as { chat: ChatThread };
      setChats((prev) =>
        prev ? prev.map((c) => (c.id === chatId ? j.chat : c)) : prev,
      );
      // Tell the viewer a reply landed. It batches a single knowledge-graph
      // evaluation when the student leaves the Chat tab, instead of one per
      // message.
      window.dispatchEvent(
        new CustomEvent("getit:chat-sent", { detail: { docId } }),
      );
    } catch (e) {
      // Roll back optimistic and surface a placeholder system message.
      setChats((prev) =>
        prev
          ? prev.map((c) =>
              c.id === chatId
                ? {
                    ...c,
                    messages: [
                      ...c.messages,
                      {
                        role: "assistant" as const,
                        content: `(reply failed — ${(e as Error).message})`,
                        ts: Date.now(),
                      },
                    ],
                  }
                : c,
            )
          : prev,
      );
    } finally {
      setSending(false);
    }
  }, [activeId, docId, draft, sending]);

  if (chats === null) {
    return (
      <div className="flex h-full items-center justify-center text-[12px] text-[var(--ink-500)]">
        <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" /> loading chats…
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Chat list */}
      <aside className="flex w-44 shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--surface-canvas)]">
        <button
          type="button"
          onClick={createChat}
          disabled={creating}
          className="m-2 flex items-center justify-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white py-1.5 text-[12px] font-medium text-[var(--ink-900)] hover:bg-[var(--surface-sunken)] disabled:opacity-60"
        >
          <Plus className="h-3.5 w-3.5" /> New chat
        </button>
        <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
          {chats.length === 0 ? (
            <p className="px-2 py-3 text-[11.5px] leading-relaxed text-[var(--ink-400)]">
              No conversations yet. Start one to ask anything about this document.
            </p>
          ) : (
            chats.map((c) => (
              <div
                key={c.id}
                className={`group flex items-center gap-1 rounded-md px-2 py-1.5 text-[12px] ${
                  activeId === c.id
                    ? "bg-white text-[var(--ink-900)] shadow-[0_1px_0_rgba(17,17,19,0.04)]"
                    : "text-[var(--ink-700)] hover:bg-white"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setActiveId(c.id)}
                  className="min-w-0 flex-1 truncate text-left"
                  title={c.title}
                >
                  {c.title}
                </button>
                <button
                  type="button"
                  onClick={() => deleteChat(c.id)}
                  className="invisible h-5 w-5 shrink-0 rounded text-[var(--ink-400)] hover:bg-[var(--surface-sunken)] hover:text-rose-600 group-hover:visible"
                  title="Delete chat"
                >
                  <Trash2 className="m-auto h-3 w-3" />
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Active thread */}
      <section className="flex min-w-0 flex-1 flex-col bg-white">
        {!active ? (
          <div className="flex flex-1 items-center justify-center px-8 text-center">
            <div className="max-w-sm">
              <MessageSquare className="mx-auto mb-3 h-7 w-7 text-[var(--ink-400)]" />
              <p className="text-[13.5px] leading-relaxed text-[var(--ink-500)]">
                Ask anything about this document. Each conversation is saved and feeds the
                knowledge graph evaluator when you leave the Chat tab.
              </p>
            </div>
          </div>
        ) : (
          <div ref={messagesRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            {active.messages.length === 0 && (
              <p className="text-center text-[12px] text-[var(--ink-400)]">
                Type your first question below.
              </p>
            )}
            {active.messages.map((m, i) => (
              <Bubble key={i} role={m.role} content={m.content} />
            ))}
            {sending && (
              <Bubble role="assistant" content="…" pulsing />
            )}
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
          className="shrink-0 border-t border-[var(--border-subtle)] bg-white p-3"
        >
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder="Ask a question about this document…"
              rows={2}
              className="min-h-[44px] flex-1 resize-none rounded-md border border-[var(--border-subtle)] bg-[var(--surface-raised)] px-3 py-2 text-[13px] leading-relaxed text-[var(--ink-900)] focus:border-[var(--accent-500)] focus:outline-none"
              disabled={sending}
            />
            <button
              type="submit"
              disabled={sending || !draft.trim()}
              className="flex h-[44px] w-[44px] items-center justify-center rounded-md bg-[var(--ink-900)] text-white hover:bg-black disabled:opacity-40"
              title="Send (Enter)"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function Bubble({
  role,
  content,
  pulsing,
}: {
  role: "user" | "assistant";
  content: string;
  pulsing?: boolean;
}) {
  const isUser = role === "user";
  return (
    <div className={`mb-3 flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-[13px] leading-relaxed ${
          isUser
            ? "bg-[var(--ink-900)] text-white"
            : "bg-[var(--surface-sunken)] text-[var(--ink-900)]"
        } ${pulsing ? "animate-pulse" : ""}`}
      >
        {content}
      </div>
    </div>
  );
}
