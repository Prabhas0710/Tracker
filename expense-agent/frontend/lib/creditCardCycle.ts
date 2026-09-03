import type { AnalyticsSummary } from "@/types/analytics";
import type { Expense } from "@/types/expense";

export type CardBank = "ICICI" | "HDFC";

export type CcBankSummary = {
  bank?: CardBank;
  cycle_start_at?: string | null;
  bill_paid_at?: string | null;
  bill_amount?: number | null;
  card_suffix?: string | null;
  cycle_spent?: number;
  due_amount?: number;
};

export function classifyCcSpendInMonth(
  spentAt: string,
  year: number,
  month: number,
  cycleStartAt: string | null | undefined,
): "current" | "due" {
  const monthStart = new Date(year, month - 1, 1);
  const monthEnd = new Date(year, month, 0, 23, 59, 59, 999);
  const spent = new Date(spentAt);
  if (!cycleStartAt) return "current";
  const cycleStart = new Date(cycleStartAt);
  if (cycleStart > monthEnd) return "due";
  if (cycleStart <= monthStart) return "current";
  return spent >= cycleStart ? "current" : "due";
}

export function ccSpendBucket(
  expense: Expense,
  year: number,
  month: number,
  summary: AnalyticsSummary | null,
): "current" | "due" | null {
  if (expense.payment_method !== "Credit Card") return null;
  const bank = expense.card_issuer as CardBank | null | undefined;
  if (!bank) return "current";
  const bankCycle = summary?.credit_card_banks?.[bank]?.cycle_start_at;
  return classifyCcSpendInMonth(expense.spent_at, year, month, bankCycle);
}

export function countsTowardCategoryTotal(
  expense: Expense,
  year: number,
  month: number,
  summary: AnalyticsSummary | null,
): boolean {
  if (expense.payment_method !== "Credit Card") return true;
  return ccSpendBucket(expense, year, month, summary) === "current";
}
