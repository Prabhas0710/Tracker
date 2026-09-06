"use client";

import { useEffect, useState } from "react";
import { formatINR } from "@/lib/utils";

type Props = {
  label?: string;
};

/** Cash-counter style loading screen while expenses fetch. */
export function CashCountLoader({ label = "Counting your spends…" }: Props) {
  const [amount, setAmount] = useState(0);

  useEffect(() => {
    let value = 0;
    let ticks = 0;
    const id = window.setInterval(() => {
      ticks += 1;
      const burst = 80 + Math.random() * 2200 + ticks * 12;
      value += burst;
      if (value > 250_000) value = 2_500 + Math.random() * 8_000;
      setAmount(value);
    }, 55);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="cash-loader" role="status" aria-live="polite" aria-busy="true">
      <div className="cash-loader-stage" aria-hidden="true">
        <span className="cash-note cash-note-a" />
        <span className="cash-note cash-note-b" />
        <span className="cash-note cash-note-c" />
        <span className="cash-coin" />
      </div>
      <strong className="cash-loader-amount">{formatINR(amount)}</strong>
      <p className="muted cash-loader-label">{label}</p>
      <div className="cash-loader-bar" aria-hidden="true">
        <span />
      </div>
    </div>
  );
}
