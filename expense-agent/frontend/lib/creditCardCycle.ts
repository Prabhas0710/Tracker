import type { AnalyticsSummary } from "@/types/analytics";
import type { Expense } from "@/types/expense";

export type CardBank = "ICICI" | "HDFC";

export const STATEMENT_DAY: Record<CardBank, number> = {
  ICICI: 6,
  HDFC: 1,
};

export type CcBankSummary = {
  bank?: CardBank;
  statement_day?: number;
  cycle_start_at?: string | null;
  bill_closes_at?: string | null;
  bill_paid_at?: string | null;
  bill_amount?: number | null;
  card_suffix?: string | null;
  cycle_spent?: number;
  unbilled_amount?: number;
  due_amount?: number;
};

export type CcSpendBucket = "bill" | "current" | "due";

function nextStatementAt(bank: CardBank, after: Date): Date {
  const day = STATEMENT_DAY[bank];
  const candidate = new Date(after.getFullYear(), after.getMonth(), day);
  if (candidate > after) return candidate;
  return new Date(after.getFullYear(), after.getMonth() + 1, day);
}

export function classifyCcSpendInMonth(
  spentAt: string,
  year: number,
  month: number,
  cycleStartAt: string | null | undefined,
  bank?: CardBank | null,
): CcSpendBucket {
  const monthStart = new Date(year, month - 1, 1);
  const monthEnd = new Date(year, month, 0, 23, 59, 59, 999);
  const spent = new Date(spentAt);

  if (!cycleStartAt) {
    if (!bank) return "bill";
    const stmt = new Date(year, month - 1, STATEMENT_DAY[bank]);
    return spent < stmt ? "bill" : "current";
  }

  const cycleStart = new Date(cycleStartAt);
  if (cycleStart > monthEnd) return "due";
  if (spent < cycleStart) return "due";

  if (!bank) return "bill";
  const billEnd = nextStatementAt(bank, cycleStart);
  return spent < billEnd ? "bill" : "current";
}

export function ccSpendBucket(
  expense: Expense,
  year: number,
  month: number,
  summary: AnalyticsSummary | null,
): CcSpendBucket | null {
  if (expense.payment_method !== "Credit Card") return null;
  const bank = expense.card_issuer as CardBank | null | undefined;
  if (!bank) return "bill";
  const bankCycle = summary?.credit_card_banks?.[bank]?.cycle_start_at;
  return classifyCcSpendInMonth(expense.spent_at, year, month, bankCycle, bank);
}

export function countsTowardCategoryTotal(
  expense: Expense,
  year: number,
  month: number,
  summary: AnalyticsSummary | null,
): boolean {
  if (expense.payment_method !== "Credit Card") return true;
  return ccSpendBucket(expense, year, month, summary) !== "due";
}
