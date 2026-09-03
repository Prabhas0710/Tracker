"use client";

import { useEffect, useMemo, useState } from "react";
import { WheelColumn, WheelSheet } from "@/components/WheelPicker";
import { api } from "@/lib/api";
import { formatINR } from "@/lib/utils";
import type { AnalyticsSummary } from "@/types/analytics";

type Domain = "expenses" | "diet";
type Period = "day" | "week" | "month" | "year";

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

function istToday() {
  const parts = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).formatToParts(new Date());
  return {
    year: Number(parts.find((p) => p.type === "year")?.value),
    month: Number(parts.find((p) => p.type === "month")?.value),
    day: Number(parts.find((p) => p.type === "day")?.value),
  };
}

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function ymd(y: number, m: number, d: number) {
  return `${y}-${pad(m)}-${pad(d)}`;
}

function shiftDay(y: number, m: number, d: number, delta: number) {
  const dt = new Date(Date.UTC(y, m - 1, d + delta));
  return { year: dt.getUTCFullYear(), month: dt.getUTCMonth() + 1, day: dt.getUTCDate() };
}

function mondayOf(y: number, m: number, d: number) {
  const js = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  const back = (js + 6) % 7;
  return shiftDay(y, m, d, -back);
}

function formatDayLabel(y: number, m: number, d: number) {
  return `${d} ${MONTH_NAMES[m - 1].slice(0, 3)} ${y}`;
}

function buildDayOptions(count = 90) {
  const today = istToday();
  const options: { value: string; label: string }[] = [];
  for (let i = 0; i < count; i += 1) {
    const next = shiftDay(today.year, today.month, today.day, -i);
    options.push({
      value: ymd(next.year, next.month, next.day),
      label: formatDayLabel(next.year, next.month, next.day),
    });
  }
  return options;
}

function buildWeekOptions(count = 26) {
  const today = istToday();
  let monday = mondayOf(today.year, today.month, today.day);
  const options: { value: string; label: string }[] = [];
  for (let i = 0; i < count; i += 1) {
    const sunday = shiftDay(monday.year, monday.month, monday.day, 6);
    options.push({
      value: ymd(monday.year, monday.month, monday.day),
      label: `${monday.day} ${MONTH_NAMES[monday.month - 1].slice(0, 3)} – ${sunday.day} ${MONTH_NAMES[sunday.month - 1].slice(0, 3)} ${sunday.year}`,
    });
    monday = shiftDay(monday.year, monday.month, monday.day, -7);
  }
  return options;
}

function buildMonthOptions(count = 18) {
  const today = istToday();
  let y = today.year;
  let m = today.month;
  const options: { year: number; month: number; label: string; value: string }[] = [];
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

function buildYearOptions(count = 5) {
  const today = istToday();
  return Array.from({ length: count }, (_, i) => {
    const year = today.year - i;
    return { value: String(year), label: String(year) };
  });
}

export default function AnalyticsPage() {
  const today = useMemo(() => istToday(), []);
  const dayOptions = useMemo(() => buildDayOptions(90), []);
  const weekOptions = useMemo(() => buildWeekOptions(26), []);
  const monthOptions = useMemo(() => buildMonthOptions(18), []);
  const yearOptions = useMemo(() => buildYearOptions(5), []);

  const [domain, setDomain] = useState<Domain>("expenses");
  const [period, setPeriod] = useState<Period>("month");
  const [date, setDate] = useState(ymd(today.year, today.month, today.day));
  const [year, setYear] = useState(today.year);
  const [month, setMonth] = useState(today.month);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draftDate, setDraftDate] = useState(ymd(today.year, today.month, today.day));
  const [draftYear, setDraftYear] = useState(today.year);
  const [draftMonth, setDraftMonth] = useState(today.month);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setSummary(null);
    api
      .getSummary(year, month, { period, date })
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load");
      });
    return () => {
      cancelled = true;
    };
  }, [year, month, period, date]);

  const triggerLabel = (() => {
    if (period === "day") {
      return dayOptions.find((option) => option.value === date)?.label || summary?.label;
    }
    if (period === "week") {
      return weekOptions.find((option) => option.value === date)?.label || summary?.label;
    }
    if (period === "year") {
      return String(year);
    }
    return monthOptions.find((option) => option.value === `${year}-${month}`)?.label || summary?.label;
  })();

  const max = summary?.by_category[0]?.amount || 1;
  const diet = summary?.diet;
  const top = summary?.top_category;

  return (
    <section className="section">
      <h2>Analytics</h2>
      <p className="lede">
        Day, week, month, and year totals from PostgreSQL — expenses and diet targets, never invented.
      </p>

      <div className="analytics-toolbar">
        <div className="payment-filter-row">
          {(["expenses", "diet"] as Domain[]).map((item) => (
            <button
              key={item}
              type="button"
              className={`payment-filter-btn${domain === item ? " active" : ""}`}
              onClick={() => setDomain(item)}
            >
              {item === "expenses" ? "Expenses" : "Diet"}
            </button>
          ))}
        </div>
        <div className="payment-filter-row">
          {(["day", "week", "month", "year"] as Period[]).map((item) => (
            <button
              key={item}
              type="button"
              className={`payment-filter-btn${period === item ? " active" : ""}`}
              onClick={() => {
                setPeriod(item);
                setPickerOpen(false);
                if (item === "day") {
                  const next = ymd(today.year, today.month, today.day);
                  setDate(next);
                  setDraftDate(next);
                }
                if (item === "week") {
                  const monday = mondayOf(today.year, today.month, today.day);
                  const next = ymd(monday.year, monday.month, monday.day);
                  setDate(next);
                  setDraftDate(next);
                }
                if (item === "month") {
                  setYear(today.year);
                  setMonth(today.month);
                }
                if (item === "year") {
                  setYear(today.year);
                }
              }}
            >
              {item[0].toUpperCase() + item.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className={`period-box${pickerOpen ? " is-open" : ""}`}>
        {!pickerOpen ? (
          <div className="month-filter">
            <button
              type="button"
              className="period-trigger"
              onClick={() => {
                setDraftDate(date);
                setDraftYear(year);
                setDraftMonth(month);
                setPickerOpen(true);
              }}
            >
              {triggerLabel}
            </button>
          </div>
        ) : (
          <WheelSheet
            title={String(triggerLabel || "Period")}
            onCancel={() => setPickerOpen(false)}
            onDone={() => {
              if (period === "day" || period === "week") {
                setDate(draftDate);
                const [y, m] = draftDate.split("-").map(Number);
                if (y) setYear(y);
                if (m) setMonth(m);
              } else if (period === "year") {
                setYear(draftYear);
              } else {
                setYear(draftYear);
                setMonth(draftMonth);
              }
              setPickerOpen(false);
            }}
          >
            {period === "day" ? (
              <WheelColumn
                ariaLabel="Day"
                value={draftDate}
                onChange={setDraftDate}
                options={dayOptions}
              />
            ) : null}
            {period === "week" ? (
              <WheelColumn
                ariaLabel="Week"
                value={draftDate}
                onChange={setDraftDate}
                options={weekOptions}
              />
            ) : null}
            {period === "month" ? (
              <WheelColumn
                ariaLabel="Month"
                value={`${draftYear}-${draftMonth}`}
                onChange={(value) => {
                  const [y, m] = value.split("-").map(Number);
                  if (!y || !m) return;
                  setDraftYear(y);
                  setDraftMonth(m);
                }}
                options={monthOptions.map((option) => ({
                  value: option.value,
                  label: option.label,
                }))}
              />
            ) : null}
            {period === "year" ? (
              <WheelColumn
                ariaLabel="Year"
                value={String(draftYear)}
                onChange={(value) => setDraftYear(Number(value))}
                options={yearOptions}
              />
            ) : null}
          </WheelSheet>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {domain === "expenses" ? (
        <>
          <div className="metric">{formatINR(summary?.total_debits ?? summary?.total_spent ?? 0)}</div>
          <p className="muted">
            {summary?.label || triggerLabel}
            {top ? ` · most spent on ${top}` : ""}
          </p>
          <div className="stack">
            {(summary?.by_category || []).map((row) => (
              <div key={row.category}>
                <div className="row">
                  <span>{row.category}</span>
                  <span>
                    {formatINR(row.amount)} ·{" "}
                    {(() => {
                      const total = summary?.total_debits ?? summary?.total_spent ?? 0;
                      return total ? Math.round((row.amount / total) * 100) : 0;
                    })()}
                    %
                  </span>
                </div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(row.amount / max) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          {summary?.insight && <p className="lede">{summary.insight}</p>}
        </>
      ) : (
        <>
          <div className="diet-stat-grid">
            <div className="diet-stat-card is-hit">
              <strong>{diet?.hit_days ?? 0}</strong>
              <span>Days hit target</span>
            </div>
            <div className="diet-stat-card is-miss">
              <strong>{diet?.missed_days ?? 0}</strong>
              <span>Days missed target</span>
            </div>
          </div>
          <p className="muted">
            {diet?.label || triggerLabel}
            {diet
              ? ` · ${diet.logged_days} logged · ${diet.no_log_days} with no meals`
              : ""}
          </p>
          {period === "day" && diet?.day ? (
            <div className="stack">
              <div className="row">
                <span>Calories</span>
                <span>
                  {diet.day.calories} / {diet.day.calorie_goal} kcal
                </span>
              </div>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{
                    width: `${Math.min(100, (diet.day.calories / Math.max(diet.day.calorie_goal, 1)) * 100)}%`,
                  }}
                />
              </div>
              <div className="row">
                <span>Protein</span>
                <span>
                  {diet.day.protein} / {diet.day.protein_goal} g
                </span>
              </div>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{
                    width: `${Math.min(100, (diet.day.protein / Math.max(diet.day.protein_goal, 1)) * 100)}%`,
                  }}
                />
              </div>
            </div>
          ) : null}
          {diet?.insight && <p className="lede">{diet.insight}</p>}
        </>
      )}
    </section>
  );
}
