"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { EditablePaymentItem } from "@/components/EditablePaymentItem";
import { WheelColumn, WheelSheet } from "@/components/WheelPicker";
import { api } from "@/lib/api";
import {
  categorySelectionPayload,
  displayCategoryName,
  sameCategorySelection,
} from "@/lib/categories";
import { formatINR } from "@/lib/utils";
import {
  countsTowardCategoryTotal,
  ccSpendBucket,
  type CardBank,
} from "@/lib/creditCardCycle";
import type { AnalyticsSummary } from "@/types/analytics";
import type { Expense } from "@/types/expense";

function istDateParts(iso: string): { year: number; month: number; day: number } {
  const parts = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).formatToParts(new Date(iso));
  return {
    year: Number(parts.find((p) => p.type === "year")?.value),
    month: Number(parts.find((p) => p.type === "month")?.value),
    day: Number(parts.find((p) => p.type === "day")?.value),
  };
}

function inSelectedPeriod(
  iso: string,
  year: number,
  month: number,
  day: number | null,
): boolean {
  const parts = istDateParts(iso);
  if (parts.year !== year || parts.month !== month) return false;
  if (day == null) return true;
  return parts.day === day;
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const MONTH_SHORT = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function istNowParts(): { year: number; month: number; day: number } {
  return istDateParts(new Date().toISOString());
}

function buildMonthOptions(count = 18) {
  const { year, month } = istNowParts();
  const options: { year: number; month: number; label: string; value: string }[] = [];
  let y = year;
  let m = month;
  for (let i = 0; i < count; i += 1) {
    options.push({
      year: y,
      month: m,
      value: `${y}-${m}`,
      label: `${MONTH_NAMES[m - 1]} ${y}`,
    });
    m -= 1;
    if (m < 1) {
      m = 12;
      y -= 1;
    }
  }
  return options;
}

export default function ExpensesOverview() {
  const todayIst = useMemo(() => istNowParts(), []);
  const monthOptions = useMemo(() => buildMonthOptions(18), []);
  const searchParams = useSearchParams();
  const router = useRouter();
  const [year, setYear] = useState(todayIst.year);
  const [month, setMonth] = useState(todayIst.month);
  const [day, setDay] = useState<number | null>(null);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [gmailNeedsReconnect, setGmailNeedsReconnect] = useState(false);
  const [gmailNote, setGmailNote] = useState<string | null>(null);
  const [gmailBusy, setGmailBusy] = useState(false);
  const [openCategory, setOpenCategory] = useState<string | null>(null);
  const [openCredits, setOpenCredits] = useState(false);
  const [paymentFilter, setPaymentFilter] = useState<"all" | "credit-card" | "debit">("all");
  const [editingExpenseId, setEditingExpenseId] = useState<number | null>(null);
  const [categoryBusy, setCategoryBusy] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draftYear, setDraftYear] = useState(todayIst.year);
  const [draftMonth, setDraftMonth] = useState(todayIst.month);
  const [draftDay, setDraftDay] = useState<number | null>(null);

  const loadSummary = async (y = year, m = month) => {
    try {
      const data = await api.getSummary(y, m);
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  };

  const loadExpenses = async (y = year, m = month) => {
    try {
      setExpenses(await api.getExpenses(y, m));
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    const flag = searchParams.get("gmail");
    if (!flag) return;
    const email = searchParams.get("email");
    const reason = searchParams.get("reason");
    if (flag === "connected") {
      setGmailNote(
        email
          ? `Connected ${email}. Connect your other inbox the same way, then wait a few seconds for sync.`
          : "Gmail connected. If you have two accounts, connect the second one too.",
      );
      setGmailNeedsReconnect(false);
      void api.gmailSync().then(async () => {
        await loadSummary(year, month);
        await loadExpenses(year, month);
        const status = await api.gmailStatus();
        setGmailNeedsReconnect(Boolean(status.needs_reconnect) || !status.connected);
      });
    } else if (flag === "error") {
      setError(reason || "Gmail connect failed");
    }
    router.replace("/expenses");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const reconnectGmail = async () => {
    setGmailBusy(true);
    setError(null);
    try {
      const result = await api.gmailReconnect();
      window.location.href = result.login_url;
    } catch (err) {
      setGmailBusy(false);
      setError(err instanceof Error ? err.message : "Could not start Gmail reconnect");
    }
  };

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      if (!alive) return;
      await Promise.all([loadSummary(year, month), loadExpenses(year, month)]);
    };
    const pullMail = async () => {
      if (!alive) return;
      try {
        const status = await api.gmailStatus();
        if (alive) setGmailNeedsReconnect(Boolean(status.needs_reconnect) || (!status.connected && (status.count ?? 0) > 0));
      } catch {
        /* ignore */
      }
      try {
        const result = await api.gmailSync();
        if (result.busy) return;
      } catch {
        /* background sync will retry */
      }
      if (alive) await refresh();
    };
    void refresh();
    const mailTimer = window.setTimeout(() => {
      void pullMail();
    }, 1500);
    const refreshId = setInterval(refresh, 12000);
    const syncId = setInterval(pullMail, 45000);
    const openAsk = (event: Event) => {
      const item = (event as CustomEvent<{ expense_id?: number | null; merchant?: string | null }>).detail;
      setOpenCategory("Needs you");
      if (item?.expense_id) setEditingExpenseId(item.expense_id);
    };
    window.addEventListener("ledgerly-open-ask", openAsk);
    return () => {
      alive = false;
      window.clearTimeout(mailTimer);
      clearInterval(refreshId);
      clearInterval(syncId);
      window.removeEventListener("ledgerly-open-ask", openAsk);
    };
  }, [year, month]);

  const toggleExpenseEdit = (expenseId: number) => {
    setEditingExpenseId((current) => (current === expenseId ? null : expenseId));
  };

  const updateExpenseCategory = async (expense: Expense, label: string) => {
    const payload = categorySelectionPayload(label);
    if (sameCategorySelection(expense, payload)) {
      setEditingExpenseId(null);
      return;
    }
    setCategoryBusy(true);
    setError(null);
    try {
      const updated = await api.updateExpense(expense.id, payload);
      setExpenses((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
      await loadSummary(year, month);
      setEditingExpenseId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update category");
    } finally {
      setCategoryBusy(false);
    }
  };

  const deleteExpense = async (expense: Expense) => {
    if (categoryBusy) return;
    setCategoryBusy(true);
    setError(null);
    try {
      await api.deleteExpense(expense.id);
      setExpenses((rows) => rows.filter((row) => row.id !== expense.id));
      if (editingExpenseId === expense.id) setEditingExpenseId(null);
      await loadSummary(year, month);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete transaction");
    } finally {
      setCategoryBusy(false);
    }
  };

  const convertExpenseDirection = async (
    expense: Expense,
    next: "debit" | "credit",
  ) => {
    if (categoryBusy) return;
    setCategoryBusy(true);
    setError(null);
    try {
      const updated = await api.updateExpense(expense.id, {
        direction: next,
        category: next === "credit" ? "Income" : expense.category === "Income" ? "Other" : expense.category,
        subcategory: next === "credit" ? null : expense.subcategory ?? null,
      });
      setExpenses((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
      await loadSummary(year, month);
      setEditingExpenseId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update transaction");
    } finally {
      setCategoryBusy(false);
    }
  };

  const isCurrentMonth = year === todayIst.year && month === todayIst.month;
  const monthShort = MONTH_SHORT[month - 1] || "";

  const draftIsCurrent =
    draftYear === todayIst.year && draftMonth === todayIst.month;
  const draftMaxDay = draftIsCurrent ? todayIst.day : daysInMonth(draftYear, draftMonth);
  const draftDayOptions = useMemo(
    () => Array.from({ length: draftMaxDay }, (_, i) => i + 1),
    [draftMaxDay],
  );

  const openPicker = () => {
    setDraftYear(year);
    setDraftMonth(month);
    setDraftDay(day);
    setPickerOpen(true);
  };

  const applyPicker = () => {
    const nextDay =
      draftDay == null ? null : Math.min(draftDay, draftMaxDay);
    if (draftYear !== year || draftMonth !== month) {
      setExpenses([]);
      setOpenCategory(null);
      setOpenCredits(false);
    }
    setYear(draftYear);
    setMonth(draftMonth);
    setDay(nextDay);
    setEditingExpenseId(null);
    setPickerOpen(false);
  };

  const onDraftMonth = (value: string) => {
    const [y, m] = value.split("-").map(Number);
    if (!y || !m) return;
    setDraftYear(y);
    setDraftMonth(m);
    const nextMax = y === todayIst.year && m === todayIst.month ? todayIst.day : daysInMonth(y, m);
    if (draftDay != null && draftDay > nextMax) setDraftDay(nextMax);
  };

  const expensesByCategory = useMemo(() => {
    const map = new Map<string, Expense[]>();
    for (const expense of expenses) {
      if (!inSelectedPeriod(expense.spent_at, year, month, day)) continue;
      if ((expense.direction || "debit") !== "debit") continue;
      const isCC = expense.payment_method === "Credit Card";
      if (paymentFilter === "credit-card" && !isCC) continue;
      if (paymentFilter === "debit" && isCC) continue;
      const label = displayCategoryName(expense.category);
      const list = map.get(label) || [];
      list.push(expense);
      map.set(label, list);
    }
    for (const [, list] of map) {
      list.sort((a, b) => +new Date(b.spent_at) - +new Date(a.spent_at));
    }
    return map;
  }, [expenses, year, month, day, paymentFilter]);

  const creditExpenses = useMemo(() => {
    return expenses
      .filter(
        (expense) =>
          inSelectedPeriod(expense.spent_at, year, month, day) &&
          (expense.direction || "debit") === "credit",
      )
      .sort((a, b) => +new Date(b.spent_at) - +new Date(a.spent_at));
  }, [expenses, year, month, day]);

  const creditsTotal = useMemo(
    () => creditExpenses.reduce((sum, e) => sum + e.amount, 0),
    [creditExpenses],
  );

  const debtsTotal = useMemo(() => {
    if (day == null) return summary?.total_debits ?? summary?.total_spent ?? 0;
    return expenses
      .filter(
        (expense) =>
          inSelectedPeriod(expense.spent_at, year, month, day) &&
          (expense.direction || "debit") === "debit",
      )
      .reduce((sum, expense) => sum + expense.amount, 0);
  }, [day, expenses, year, month, summary]);

  const spendRows = useMemo(() => {
    return Array.from(expensesByCategory.entries())
      .map(([category, items]) => ({
        category,
        items,
        amount: items.reduce(
          (sum, expense) =>
            sum + (countsTowardCategoryTotal(expense, year, month, summary) ? expense.amount : 0),
          0,
        ),
        attention: category.toLowerCase() === "needs review",
      }))
      .filter((row) => row.items.length > 0)
      .sort((a, b) => b.amount - a.amount);
  }, [expensesByCategory, year, month, summary]);

  const reviewRow = spendRows.find((row) => row.attention);
  const visibleRows = spendRows.filter((row) => !row.attention);
  const maxSpend = visibleRows[0]?.amount || 1;
  const netTotal = creditsTotal - debtsTotal;

  const toggleCategory = (category: string) => {
    setOpenCategory((current) => (current === category ? null : category));
  };

  return (
    <section className="section">
      <h2>Expenses</h2>

      {gmailNeedsReconnect && (
        <button
          type="button"
          className="gmail-reconnect-banner"
          onClick={() => void reconnectGmail()}
          disabled={gmailBusy}
        >
          {gmailBusy
            ? "Opening Google…"
            : "Gmail access expired — tap here to reconnect (do both accounts)"}
        </button>
      )}
      {gmailNote && <p className="ok">{gmailNote}</p>}

      {error && <p className="error">{error}</p>}

      <div className={`period-box${pickerOpen ? " is-open" : ""}`}>
        {!pickerOpen ? (
          <div className="month-filter">
            <button type="button" className="period-trigger" onClick={openPicker}>
              {MONTH_NAMES[month - 1]} {year}
            </button>
            <button type="button" className="period-trigger period-trigger-day" onClick={openPicker}>
              {day == null ? "All days" : `${day} ${monthShort}`}
            </button>
          </div>
        ) : (
          <WheelSheet title={`${MONTH_NAMES[draftMonth - 1]} ${draftYear}`} onCancel={() => setPickerOpen(false)} onDone={applyPicker}>
            <WheelColumn
              ariaLabel="Month"
              value={`${draftYear}-${draftMonth}`}
              onChange={onDraftMonth}
              options={monthOptions.map((option) => ({
                value: option.value,
                label: option.label,
              }))}
            />
            <WheelColumn
              ariaLabel="Day"
              value={draftDay == null ? "" : String(draftDay)}
              onChange={(value) => setDraftDay(value ? Number(value) : null)}
              options={[
                { value: "", label: "All days" },
                ...draftDayOptions.map((d) => ({
                  value: String(d),
                  label: `${d} ${MONTH_SHORT[draftMonth - 1]}`,
                })),
              ]}
            />
          </WheelSheet>
        )}
      </div>
      {!isCurrentMonth && (
        <button
          type="button"
          className="btn btn-ghost"
          style={{ justifySelf: "start", padding: "0.4rem 0.85rem", fontSize: "0.85rem" }}
          onClick={() => {
            setYear(todayIst.year);
            setMonth(todayIst.month);
            setDay(null);
            setOpenCategory(null);
            setOpenCredits(false);
            setEditingExpenseId(null);
          }}
        >
          This month
        </button>
      )}

      <div className="metric">{formatINR(debtsTotal)}</div>
      <p className="muted spend-caption">
        Spent {day == null ? "this month" : "this day"}
      </p>

      <div className="snapshot">
        <div>
          <span className="snapshot-label">In</span>
          <strong className="ok">+{formatINR(creditsTotal)}</strong>
        </div>
        <div>
          <span className="snapshot-label">Net</span>
          <strong className={netTotal >= 0 ? "ok" : undefined}>{formatINR(netTotal)}</strong>
        </div>
        <div>
          <span className="snapshot-label">Top</span>
          <strong>{visibleRows[0]?.category || "—"}</strong>
        </div>
      </div>

      <aside className="cc-due-panel cc-due-panel-top" aria-label="Credit card dues">
        <h3 className="cc-due-title">To pay next bill</h3>
        <p className="muted cc-due-sub">Current cycle · after last bill paid</p>
        <div className="cc-due-total">
          <span>Total credit bill</span>
          <strong>
            {formatINR(
              (["ICICI", "HDFC"] as CardBank[]).reduce(
                (sum, bank) => sum + (summary?.credit_card_banks?.[bank]?.cycle_spent ?? 0),
                0,
              ),
            )}
          </strong>
        </div>
        <div className="cc-due-banks">
          {(["ICICI", "HDFC"] as CardBank[]).map((bank) => {
            const row = summary?.credit_card_banks?.[bank];
            const alreadyPaid = row?.due_amount ?? 0;
            const toPay = row?.cycle_spent ?? 0;
            return (
              <div key={bank} className="cc-due-card">
                <div className="row cc-due-main" style={{ borderBottom: 0, padding: "0.35rem 0" }}>
                  <span>{bank}</span>
                  <strong className="cc-due-amount">{formatINR(toPay)}</strong>
                </div>
                {alreadyPaid > 0 && row?.bill_paid_at && (
                  <p className="muted cc-due-settled">
                    Already paid: {formatINR(alreadyPaid)}
                    {` · before ${new Date(row.bill_paid_at).toLocaleDateString("en-IN", {
                      timeZone: "Asia/Kolkata",
                      day: "numeric",
                      month: "short",
                    })}`}
                  </p>
                )}
                {row?.bill_paid_at && (
                  <p className="muted cc-due-meta">
                    Last bill paid{" "}
                    {new Date(row.bill_paid_at).toLocaleDateString("en-IN", {
                      timeZone: "Asia/Kolkata",
                      day: "numeric",
                      month: "short",
                    })}
                    {row.bill_amount ? ` · ${formatINR(row.bill_amount)}` : ""}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      <div className="spend-board">
        <div className="payment-filter-row" role="tablist" aria-label="Payment source">
          <button
            type="button"
            className={`payment-filter-btn${paymentFilter === "all" ? " active" : ""}`}
            onClick={() => { setPaymentFilter("all"); setOpenCategory(null); }}
          >
            All
          </button>
          <button
            type="button"
            className={`payment-filter-btn${paymentFilter === "debit" ? " active" : ""}`}
            onClick={() => { setPaymentFilter("debit"); setOpenCategory(null); }}
          >
            Bank & UPI
          </button>
          <button
            type="button"
            className={`payment-filter-btn${paymentFilter === "credit-card" ? " active" : ""}`}
            onClick={() => { setPaymentFilter("credit-card"); setOpenCategory(null); }}
          >
            Cards
          </button>
        </div>

        {paymentFilter === "credit-card" && summary?.credit_card_cycle?.bill_paid_at && (
          <p className="muted filter-note">
            Card spend since{" "}
            {new Date(summary.credit_card_cycle.bill_paid_at).toLocaleDateString("en-IN", {
              timeZone: "Asia/Kolkata",
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </p>
        )}

        {reviewRow && (
          <button
            type="button"
            className="review-chip"
            onClick={() => toggleCategory(reviewRow.category)}
          >
            {reviewRow.items.length} payment{reviewRow.items.length === 1 ? "" : "s"} need a category
          </button>
        )}

        <div className="spend-list">
          {visibleRows.length === 0 && creditExpenses.length === 0 ? (
            <p className="muted empty-state">
              {paymentFilter === "credit-card"
                ? "No card transactions this period."
                : paymentFilter === "debit"
                  ? "No bank or UPI transactions this period."
                  : "No transactions this period."}
            </p>
          ) : (
            <>
              {visibleRows.map((row) => {
                const open = openCategory === row.category;
                const share = maxSpend ? Math.max(6, (row.amount / maxSpend) * 100) : 0;
                return (
                  <div key={row.category} className={`spend-row${open ? " is-open" : ""}`}>
                    <button
                      type="button"
                      className="spend-row-toggle"
                      onClick={() => toggleCategory(row.category)}
                      aria-expanded={open}
                    >
                      <span className="spend-row-copy">
                        <span className="spend-row-name">{row.category}</span>
                        <span className="spend-row-meta">{row.items.length}</span>
                      </span>
                      <span className="spend-row-bar" aria-hidden="true">
                        <span className="spend-row-fill" style={{ width: `${share}%` }} />
                      </span>
                      <strong className="spend-row-amount">{formatINR(row.amount)}</strong>
                    </button>
                    {open && (
                      <div className="payment-list">
                        {row.items.map((expense) => (
                          <EditablePaymentItem
                            key={expense.id}
                            expense={expense}
                            isOpen={editingExpenseId === expense.id}
                            onToggle={() => toggleExpenseEdit(expense.id)}
                            onCategorySelect={(cat) => updateExpenseCategory(expense, cat)}
                            onDelete={() => void deleteExpense(expense)}
                            onMakeIncome={() => void convertExpenseDirection(expense, "credit")}
                            onMakeExpense={() => void convertExpenseDirection(expense, "debit")}
                            disabled={categoryBusy}
                            footer={
                              ccSpendBucket(expense, year, month, summary) === "due"
                                ? <div className="muted payment-paid-tag">Already paid</div>
                                : undefined
                            }
                          />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}

              {reviewRow && openCategory === reviewRow.category && (
                <div className="spend-row is-open">
                  <div className="payment-list">
                    {reviewRow.items.map((expense) => (
                      <EditablePaymentItem
                        key={expense.id}
                        expense={expense}
                        isOpen={editingExpenseId === expense.id}
                        onToggle={() => toggleExpenseEdit(expense.id)}
                        onCategorySelect={(cat) => updateExpenseCategory(expense, cat)}
                        onDelete={() => void deleteExpense(expense)}
                        onMakeIncome={() => void convertExpenseDirection(expense, "credit")}
                        onMakeExpense={() => void convertExpenseDirection(expense, "debit")}
                        disabled={categoryBusy}
                      />
                    ))}
                  </div>
                </div>
              )}

              {creditExpenses.length > 0 && (
                <div className={`spend-row spend-row-credit${openCredits ? " is-open" : ""}`}>
                  <button
                    type="button"
                    className="spend-row-toggle"
                    onClick={() => setOpenCredits((v) => !v)}
                    aria-expanded={openCredits}
                  >
                    <span className="spend-row-copy">
                      <span className="spend-row-name">Income</span>
                      <span className="spend-row-meta">{creditExpenses.length}</span>
                    </span>
                    <span className="spend-row-bar" aria-hidden="true" />
                    <strong className="spend-row-amount ok">+{formatINR(creditsTotal)}</strong>
                  </button>
                  {openCredits && (
                    <div className="payment-list">
                      {creditExpenses.map((expense) => (
                        <EditablePaymentItem
                          key={expense.id}
                          expense={expense}
                          isOpen={editingExpenseId === expense.id}
                          onToggle={() => toggleExpenseEdit(expense.id)}
                          onCategorySelect={(category) => updateExpenseCategory(expense, category)}
                          onDelete={() => void deleteExpense(expense)}
                          onMakeIncome={() => void convertExpenseDirection(expense, "credit")}
                          onMakeExpense={() => void convertExpenseDirection(expense, "debit")}
                          disabled={categoryBusy}
                          amountClassName="ok"
                          amountPrefix="+"
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
