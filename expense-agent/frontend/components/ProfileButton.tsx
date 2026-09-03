"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

const THEME_KEY = "ledgerly-theme";

const user = {
  fullName: "Prabhas",
  email: "user@expense.local",
  initials: "P",
};

type Theme = "dark" | "light";

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "light" ? "#f4f8fc" : "#03060c");
}

function MenuItem({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button type="button" className="user-btn__menu-item" onClick={onClick}>
      {children}
    </button>
  );
}

export default function ProfileButton() {
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>("dark");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(THEME_KEY);
    const next: Theme = stored === "light" || stored === "dark" ? stored : "dark";
    setTheme(next);
    applyTheme(next);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    window.localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  };

  const signOut = () => {
    setOpen(false);
    window.location.href = "/";
  };

  return (
    <div className={`user-btn__root${open ? " is-open" : ""}`} ref={rootRef}>
      <button
        type="button"
        className="user-btn__closed"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label="Open profile menu"
      >
        <span className="user-btn__avatar">{user.initials}</span>
      </button>
      {open && (
        <div className="user-btn__open">
          <div className="user-btn__menu-header">
            <div className="user-btn__menu-avatar-wrap">
              <div className="user-btn__avatar user-btn__avatar--large">{user.initials}</div>
            </div>
            <div className="user-btn__menu-header-content">
              <p>{user.fullName}</p>
              <p>{user.email}</p>
            </div>
          </div>
          <div className="user-btn__menu-content">
            <MenuItem onClick={toggleTheme}>{theme === "dark" ? "Light theme" : "Dark theme"}</MenuItem>
            <MenuItem onClick={signOut}>Sign out</MenuItem>
            <p className="user-btn__brand">Ledgerly</p>
          </div>
        </div>
      )}
    </div>
  );
}
