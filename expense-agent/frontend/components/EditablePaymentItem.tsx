"use client";

import { type ReactNode, useRef, useState } from "react";
import { CategoryEditor } from "@/components/CategoryEditor";
import { expenseCategoryLabel } from "@/lib/categories";
import { creditCardViaLabel } from "@/lib/paymentLabels";
import { formatINR } from "@/lib/utils";
import type { Expense } from "@/types/expense";

const ACTION_W = 88;
const THRESHOLD = 56;

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
  onDelete?: () => void;
  onMakeIncome?: () => void;
  onMakeExpense?: () => void;
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
  onDelete,
  onMakeIncome,
  onMakeExpense,
  disabled = false,
  amountClassName,
  amountPrefix = "",
  footer,
}: Props) {
  const direction = expense.direction || "debit";
  const canIncome = direction === "debit" && Boolean(onMakeIncome);
  const canExpense = direction === "credit" && Boolean(onMakeExpense);
  const [offset, setOffset] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const offsetRef = useRef(0);
  const startX = useRef(0);
  const startY = useRef(0);
  const startOffset = useRef(0);
  const locking = useRef<"h" | "v" | null>(null);
  const swiping = useRef(false);

  const setSwipeOffset = (next: number) => {
    offsetRef.current = next;
    setOffset(next);
  };

  const snap = (next: number) => {
    if (next <= -THRESHOLD && onDelete) setSwipeOffset(-ACTION_W);
    else if (next >= THRESHOLD && (canIncome || canExpense)) setSwipeOffset(ACTION_W);
    else setSwipeOffset(0);
  };

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (disabled || isOpen) return;
    startX.current = event.clientX;
    startY.current = event.clientY;
    startOffset.current = offsetRef.current;
    locking.current = null;
    swiping.current = false;
    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (disabled || isOpen || !event.currentTarget.hasPointerCapture(event.pointerId)) return;
    const dx = event.clientX - startX.current;
    const dy = event.clientY - startY.current;
    if (!locking.current) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      locking.current = Math.abs(dx) > Math.abs(dy) ? "h" : "v";
    }
    if (locking.current !== "h") return;
    swiping.current = true;
    let next = startOffset.current + dx;
    const min = onDelete ? -ACTION_W : 0;
    const max = canIncome || canExpense ? ACTION_W : 0;
    next = Math.max(min, Math.min(max, next));
    setSwipeOffset(next);
  };

  const onPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setIsDragging(false);
    if (locking.current === "h") snap(offsetRef.current);
    locking.current = null;
  };

  const handleToggle = () => {
    if (swiping.current || Math.abs(offsetRef.current) > 8) {
      setSwipeOffset(0);
      return;
    }
    onToggle();
  };

  return (
    <div className="expense-edit-block payment-edit-block">
      <div className="payment-swipe">
        <div className="payment-swipe-actions" aria-hidden={offset === 0}>
          <button
            type="button"
            className="payment-swipe-btn is-income"
            disabled={disabled || (!canIncome && !canExpense)}
            onClick={() => {
              setSwipeOffset(0);
              if (canIncome) onMakeIncome?.();
              else if (canExpense) onMakeExpense?.();
            }}
          >
            {canExpense ? "Expense" : "Income"}
          </button>
          <button
            type="button"
            className="payment-swipe-btn is-delete"
            disabled={disabled || !onDelete}
            onClick={() => {
              setSwipeOffset(0);
              onDelete?.();
            }}
          >
            Delete
          </button>
        </div>
        <div
          className="payment-swipe-front"
          style={{
            transform: `translateX(${offset}px)`,
            transition: isDragging ? "none" : "transform 160ms ease",
          }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <button
            type="button"
            className="payment-item payment-item-toggle"
            onClick={handleToggle}
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
        </div>
      </div>
      {isOpen && (
        <div className="payment-category-editor">
          <p className="muted" style={{ fontSize: "0.82rem", marginBottom: "0.55rem" }}>
            Change category
          </p>
          <CategoryEditor
            current={expenseCategoryLabel(expense)}
            includeIncome={direction === "credit"}
            disabled={disabled}
            onSelect={onCategorySelect}
          />
        </div>
      )}
    </div>
  );
}
