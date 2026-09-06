"use client";

import { useEffect, useState } from "react";

const EXIT_MS = 380;
const MIN_MS = 1200;
const MAX_MS = 15000;
const SEEN_KEY = "nutrifin-splash-seen";

/**
 * Full-screen NUTRIFIN intro on a fresh site/app open only.
 * Stays until the first page signals ready (or max timeout).
 */
export default function NutrifinSplash() {
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    try {
      if (sessionStorage.getItem(SEEN_KEY)) return;
      sessionStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* still show once this mount */
    }

    setVisible(true);

    let ready = false;
    let minDone = false;
    let closed = false;

    const close = () => {
      if (closed) return;
      closed = true;
      setExiting(true);
      window.setTimeout(() => setVisible(false), EXIT_MS);
    };

    const tryClose = () => {
      if (ready && minDone) close();
    };

    const onReady = () => {
      ready = true;
      tryClose();
    };

    window.addEventListener("nutrifin-ready", onReady);
    const minTimer = window.setTimeout(() => {
      minDone = true;
      tryClose();
    }, MIN_MS);
    const maxTimer = window.setTimeout(close, MAX_MS);

    return () => {
      window.removeEventListener("nutrifin-ready", onReady);
      window.clearTimeout(minTimer);
      window.clearTimeout(maxTimer);
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
