"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { ChatConversation } from "@/types/analytics";

function startOfDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function groupLabel(iso: string, now = new Date()) {
  const then = new Date(iso);
  const diffDays = Math.round((startOfDay(now) - startOfDay(then)) / 86_400_000);
  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return "Previous 7 days";
  if (diffDays < 30) return "Previous 30 days";
  return then.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

function timeLabel(iso: string) {
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function HistoryPage() {
  const [rows, setRows] = useState<ChatConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setRows(await api.getChatConversations());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load chats");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const groups = useMemo(() => {
    const map = new Map<string, ChatConversation[]>();
    for (const row of rows) {
      const label = groupLabel(row.updated_at);
      const list = map.get(label) ?? [];
      list.push(row);
      map.set(label, list);
    }
    return Array.from(map.entries());
  }, [rows]);

  const remove = async (id: number) => {
    const ok = window.confirm("Delete this chat?");
    if (!ok) return;
    try {
      await api.deleteChatConversation(id);
      setRows((current) => current.filter((row) => row.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete chat");
    }
  };

  return (
    <section className="section history-page">
      <div className="history-head">
        <div>
          <h2>History</h2>
          <p className="lede">All your chats, newest first.</p>
        </div>
        <Link className="history-new" href="/?new=1">
          New chat
        </Link>
      </div>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}

      {!loading && rows.length === 0 && (
        <div className="history-empty">
          <p>No chats yet. Ask something on Chat and it will show up here.</p>
          <Link className="history-new" href="/">
            Go to Chat
          </Link>
        </div>
      )}

      {groups.map(([label, items]) => (
        <div key={label} className="history-group">
          <h3 className="history-group-label">{label}</h3>
          <div className="history-list">
            {items.map((row) => (
              <div key={row.id} className="history-row">
                <Link className="history-link" href={`/?c=${row.id}`}>
                  <strong>{row.title}</strong>
                  {row.preview && <span>{row.preview}</span>}
                  <em>{timeLabel(row.updated_at)}</em>
                </Link>
                <button
                  type="button"
                  className="history-delete"
                  aria-label={`Delete ${row.title}`}
                  title="Delete"
                  onClick={() => void remove(row.id)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      fill="currentColor"
                      d="M9 3h6l1 2h4v2H4V5h4zm1 6h2v9h-2zm4 0h2v9h-2zM7 8h10l-.8 11.1A2 2 0 0 1 14.21 21H9.79a2 2 0 0 1-1.99-1.9z"
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
