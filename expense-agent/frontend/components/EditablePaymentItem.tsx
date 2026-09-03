"use client";

import type { ReactNode } from "react";
import { CategoryEditor } from "@/components/CategoryEditor";
import { expenseCategoryLabel } from "@/lib/categories";
import { creditCardViaLabel } from "@/lib/paymentLabels";
import { formatINR } from "@/lib/utils";
import type { Expense } from "@/types/expense";

export function paymentLabel(expense: Expense): string {
  const parts = [expense.merchant, expense.description, expense.subcategory].filter(
    Boolean,
  ) as string[];
  if (!parts.length) return "Payment";
  const label = parts[0];
  return label.length > 48 ? `${label.slice(0, 48)}…` : label;
}

function paymentRef(expense: Expense): string | null {
  const ref = expense.upi_ref || expense.reference_id;
  if (!ref) return null;
  const lower = ref.toLowerCase();
  if (lower === "unknown" || lower === "n/a" || lower === "none") return null;
  if (ref.includes(":") && !/^\d+$/.test(ref.split(":").pop() || "")) return null;
  const clean = ref.startsWith("upi:") ? ref.slice(4) : ref;
  return clean || null;
}

function categoryLabel(expense: Expense): string {
  return expenseCategoryLabel(expense);
}

function PaymentMeta({ expense }: { expense: Expense }) {
  const ref = paymentRef(expense);
  const cardVia = creditCardViaLabel(expense);
  return (
    <>
      <div className="muted" style={{ fontSize: "0.78rem" }}>
        {new Date(expense.spent_at).toLocaleString("en-IN", {
          timeZone: "Asia/Kolkata",
          day: "numeric",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        })}
        {` · ${categoryLabel(expense)}`}
        {cardVia ? ` · ${cardVia}` : ""}
      </div>
      {ref && (
        <div className="muted payment-ref" style={{ fontSize: "0.72rem" }}>
          Ref: {ref}
        </div>
      )}
    </>
  );
}

type Props = {
  expense: Expense;
  isOpen: boolean;
  onToggle: () => void;
  onCategorySelect: (category: string) => void;
  disabled?: boolean;
  amountClassName?: string;
  amountPrefix?: string;
  footer?: ReactNode;
};

export function EditablePaymentItem({
  expense,
  isOpen,
  onToggle,
  onCategorySelect,
  disabled = false,
  amountClassName,
  amountPrefix = "",
  footer,
}: Props) {
  return (
    <div className="expense-edit-block payment-edit-block">
      <button
        type="button"
        className="payment-item payment-item-toggle"
        onClick={onToggle}
        aria-expanded={isOpen}
      >
        <div>
          <div className="payment-label">{paymentLabel(expense)}</div>
          <PaymentMeta expense={expense} />
          {footer}
        </div>
        <strong className={amountClassName}>
          {amountPrefix}
          {formatINR(expense.amount)}
        </strong>
      </button>
      {isOpen && (
        <div className="payment-category-editor">
          <p className="muted" style={{ fontSize: "0.82rem", marginBottom: "0.55rem" }}>
            Change category
          </p>
          <CategoryEditor
            current={expenseCategoryLabel(expense)}
            includeIncome={(expense.direction || "debit") === "credit"}
            disabled={disabled}
            onSelect={onCategorySelect}
          />
        </div>
      )}
    </div>
  );
}
