"use client";

import { useEffect, useRef, type ReactNode } from "react";

export type WheelOption = { value: string; label: string };

const ITEM_H = 44;
const VISIBLE = 5;
const PAD = 2;

export function WheelColumn({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: WheelOption[];
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const timer = useRef<number>(0);

  const indexOf = (next: string) => {
    const found = options.findIndex((option) => option.value === next);
    return found < 0 ? 0 : found;
  };

  const jumpTo = (i: number) => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = i * ITEM_H;
  };

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => jumpTo(indexOf(value)));
    return () => window.cancelAnimationFrame(frame);
    // Only align when the sheet opens or the option list changes — not while spinning.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.map((o) => o.value).join("|")]);

  const settle = () => {
    const el = scroller.current;
    if (!el || !options.length) return;
    const i = Math.min(options.length - 1, Math.max(0, Math.round(el.scrollTop / ITEM_H)));
    el.scrollTo({ top: i * ITEM_H, behavior: "smooth" });
    const next = options[i];
    if (next && next.value !== value) onChange(next.value);
  };

  return (
    <div className="wheel-col" style={{ height: ITEM_H * VISIBLE }}>
      <div className="wheel-highlight" style={{ height: ITEM_H }} />
      <div
        ref={scroller}
        className="wheel-scroll"
        role="listbox"
        aria-label={ariaLabel}
        onScroll={() => {
          if (dragging.current) return;
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(settle, 90);
        }}
        onTouchStart={() => {
          dragging.current = true;
        }}
        onTouchEnd={() => {
          dragging.current = false;
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(settle, 60);
        }}
      >
        <div className="wheel-spacer" style={{ height: ITEM_H * PAD }} />
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <div
              key={option.value || "all"}
              role="option"
              aria-selected={selected}
              className={`wheel-item${selected ? " is-selected" : ""}`}
              style={{ height: ITEM_H }}
              onClick={() => {
                onChange(option.value);
                jumpTo(indexOf(option.value));
              }}
            >
              {option.label}
            </div>
          );
        })}
        <div className="wheel-spacer" style={{ height: ITEM_H * PAD }} />
      </div>
    </div>
  );
}

export function WheelSheet({
  title,
  onCancel,
  onDone,
  children,
}: {
  title: string;
  onCancel: () => void;
  onDone: () => void;
  children: ReactNode;
}) {
  return (
    <div className="wheel-inline" role="dialog" aria-label={title}>
      <header className="wheel-sheet-head">
        <button type="button" className="wheel-sheet-action" onClick={onCancel}>
          Cancel
        </button>
        <strong>{title}</strong>
        <button type="button" className="wheel-sheet-action is-done" onClick={onDone}>
          Done
        </button>
      </header>
      <div className="wheel-sheet-body">{children}</div>
    </div>
  );
}
