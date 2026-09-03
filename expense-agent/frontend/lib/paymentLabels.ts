import type { Expense } from "@/types/expense";

/** e.g. "via HDFC Credit Card" or "via ICICI Credit Card · 8308" */
export function creditCardViaLabel(expense: Expense): string | null {
  if (expense.payment_method !== "Credit Card") return null;
  const issuer = expense.card_issuer?.trim();
  if (!issuer) return "via Credit Card";
  const suffix = expense.account_suffix?.trim();
  const label = `${issuer} Credit Card`;
  return suffix ? `via ${label} · ${suffix}` : `via ${label}`;
}
