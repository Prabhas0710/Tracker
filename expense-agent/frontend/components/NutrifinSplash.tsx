"use client";

import { useEffect, useState } from "react";

const SHOW_MS = 2000;
const EXIT_MS = 350;
const SEEN_KEY = "nutrifin-splash-seen";

/**
 * NUTRIFIN intro — only on a fresh site/app open (once per browser tab session).
 * Not shown again while navigating between pages in the same session.
 */
export default function NutrifinSplash() {
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    try {
      if (sessionStorage.getItem(SEEN_KEY)) return;
      sessionStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* private mode — still show once this mount */
    }

    setVisible(true);
    const exitAt = window.setTimeout(() => setExiting(true), SHOW_MS - EXIT_MS);
    const hideAt = window.setTimeout(() => setVisible(false), SHOW_MS);
    return () => {
      window.clearTimeout(exitAt);
      window.clearTimeout(hideAt);
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      className={`nutrifin-splash${exiting ? " is-exit" : ""}`}
      role="status"
      aria-live="polite"
      aria-label="NUTRIFIN"
    >
      <p className="nutrifin-splash-mark">NUTRIFIN</p>
    </div>
  );
}
