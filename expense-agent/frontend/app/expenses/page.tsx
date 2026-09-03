"use client";

import { Suspense } from "react";
import ExpensesOverview from "@/components/ExpensesOverview";

export default function Page() {
  return (
    <Suspense
      fallback={
        <section className="section">
          <h2>Expenses</h2>
          <p className="muted">Loading…</p>
        </section>
      }
    >
      <ExpensesOverview />
    </Suspense>
  );
}
