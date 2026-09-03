"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type GmailState = "unknown" | "ok" | "expired" | "off";

export default function GmailStatusDot() {
  const [state, setState] = useState<GmailState>("unknown");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const status = await api.gmailStatus();
        if (!alive) return;
        if (status.connected && !status.needs_reconnect) setState("ok");
        else if (status.needs_reconnect || (status.count ?? 0) > 0) setState("expired");
        else setState("off");
      } catch {
        if (alive) setState("off");
      }
    };
    tick();
    const id = setInterval(tick, 8000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const tone = state === "ok" ? "is-on" : state === "expired" || state === "off" ? "is-off" : "";
  const title =
    state === "ok"
      ? "Gmail connected"
      : state === "expired"
        ? "Gmail access expired — click to reconnect"
        : state === "off"
          ? "Gmail not connected — click to connect"
          : "Gmail";

  const onClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (state === "expired") {
        const result = await api.gmailReconnect();
        window.location.assign(result.login_url.startsWith("http") ? result.login_url : "/api/auth/gmail/login");
        return;
      }
      window.location.assign("/api/auth/gmail/login");
    } catch {
      window.location.assign("/api/auth/gmail/login");
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      className={["gmail-dot", tone].filter(Boolean).join(" ")}
      title={title}
      aria-label={title}
      onClick={() => void onClick()}
      disabled={busy}
    />
  );
}
