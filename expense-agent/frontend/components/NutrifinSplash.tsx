"use client";

import { useEffect, useState } from "react";

const SHOW_MS = 2000;
const EXIT_MS = 320;

/** Full-screen NUTRIFIN intro shown for ~2s when the site opens. */
export default function NutrifinSplash() {
  const [visible, setVisible] = useState(true);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
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
      <div className="nutrifin-splash-glow" aria-hidden="true" />
      <p className="nutrifin-splash-mark" aria-hidden="true">
        {"NUTRIFIN".split("").map((letter, index) => (
          <span key={`${letter}-${index}`} style={{ animationDelay: `${80 + index * 70}ms` }}>
            {letter}
          </span>
        ))}
      </p>
      <span className="sr-only">NUTRIFIN</span>
    </div>
  );
}
