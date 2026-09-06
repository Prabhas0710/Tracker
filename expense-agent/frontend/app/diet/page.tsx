"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { CookingLoader } from "@/components/CookingLoader";
import { api } from "@/lib/api";
import { signalNutrifinReady } from "@/lib/nutrifinReady";
import type { DietDay, DietMonth, MealEstimate, MealType } from "@/types/diet";

const MEAL_TYPES: MealType[] = ["Breakfast", "Lunch", "Dinner", "Snack"];

function todayIst(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const year = parts.find((p) => p.type === "year")?.value;
  const month = parts.find((p) => p.type === "month")?.value;
  const day = parts.find((p) => p.type === "day")?.value;
  return `${year}-${month}-${day}`;
}

function shiftDate(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const next = new Date(Date.UTC(y, m - 1, d + days));
  return next.toISOString().slice(0, 10);
}

function prettyDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-IN", {
    timeZone: "UTC",
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

function monthKeyFromDate(iso: string): string {
  return iso.slice(0, 7);
}

function monthTitle(monthKey: string): string {
  const [y, m] = monthKey.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-IN", {
    timeZone: "UTC",
    month: "long",
    year: "numeric",
  });
}

function buildMonthGrid(monthKey: string): string[] {
  const [y, m] = monthKey.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1, 1));
  const firstWeekday = first.getUTCDay();
  const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const cells: string[] = [];
  for (let i = 0; i < firstWeekday; i += 1) cells.push("");
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push(`${monthKey}-${String(day).padStart(2, "0")}`);
  }
  return cells;
}

function kcal(value: number): string {
  return `${Math.round(value).toLocaleString("en-IN")} kcal`;
}

function grams(value: number | null | undefined): string {
  if (value == null) return "0";
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <rect x="3.5" y="5.5" width="17" height="15" rx="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3.5 9.5h17" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 3.5v4M16 3.5v4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function liters(ml: number): string {
  const value = ml / 1000;
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export default function DietPage() {
  const today = useMemo(() => todayIst(), []);
  const [date, setDate] = useState(today);
  const [day, setDay] = useState<DietDay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [estimating, setEstimating] = useState(false);
  const [name, setName] = useState("");
  const [calories, setCalories] = useState("");
  const [mealType, setMealType] = useState<MealType>("Breakfast");
  const [protein, setProtein] = useState("");
  const [carbs, setCarbs] = useState("");
  const [fat, setFat] = useState("");
  const [fiber, setFiber] = useState("");
  const [estimateSource, setEstimateSource] = useState<MealEstimate["source"] | null>(null);
  const [goalDraft, setGoalDraft] = useState("");
  const [proteinGoalDraft, setProteinGoalDraft] = useState("");
  const [openType, setOpenType] = useState<string | null>("Breakfast");
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarMonth, setCalendarMonth] = useState(monthKeyFromDate(today));
  const [monthData, setMonthData] = useState<DietMonth | null>(null);
  const [goalsOpen, setGoalsOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const estimateSeq = useRef(0);

  const load = async (nextDate = date) => {
    try {
      const data = await api.getDietDay(nextDate);
      setDay(data);
      setGoalDraft(String(Math.round(data.calorie_goal)));
      setProteinGoalDraft(String(Math.round(data.protein_goal)));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load diet");
    }
  };

  const loadMonth = async (month = calendarMonth) => {
    try {
      const data = await api.getDietMonth(month);
      setMonthData(data);
      if (data.streak_broken && data.streak_ended_length) {
        setMessage(
          `Your ${data.streak_ended_length}-day streak has come to an end 😢 Starting fresh — past ★ days stay on the calendar.`,
        );
      }
    } catch {
      setMonthData(null);
    }
  };

  useEffect(() => {
    let alive = true;
    setPageLoading(true);
    setDay(null);
    (async () => {
      try {
        const data = await api.getDietDay(date);
        if (!alive) return;
        setDay(data);
        setGoalDraft(String(Math.round(data.calorie_goal)));
        setProteinGoalDraft(String(Math.round(data.protein_goal)));
        setError(null);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "Could not load diet");
      } finally {
        if (alive) {
          setPageLoading(false);
          signalNutrifinReady();
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [date]);

  useEffect(() => {
    setCalendarMonth(monthKeyFromDate(date));
  }, [date]);

  useEffect(() => {
    void loadMonth(calendarMonth);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calendarMonth]);

  useEffect(() => {
    const food = name.trim();
    if (food.length < 3) {
      setEstimating(false);
      setEstimateSource(null);
      return;
    }
    const seq = ++estimateSeq.current;
    setEstimating(true);
    const timer = window.setTimeout(async () => {
      try {
        const estimate = await api.estimateMeal(food);
        if (seq !== estimateSeq.current) return;
        setCalories(String(Math.round(estimate.calories)));
        setProtein(grams(estimate.protein));
        setCarbs(grams(estimate.carbs));
        setFat(grams(estimate.fat));
        setFiber(grams(estimate.fiber));
        setEstimateSource(estimate.source ?? "ai");
        setError(null);
      } catch (err) {
        if (seq !== estimateSeq.current) return;
        setError(err instanceof Error ? err.message : "Could not estimate nutrition");
      } finally {
        if (seq === estimateSeq.current) setEstimating(false);
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [name]);

  const grouped = useMemo(() => {
    const map = new Map<string, DietDay["meals"]>();
    for (const type of MEAL_TYPES) map.set(type, []);
    for (const meal of day?.meals || []) {
      const key = MEAL_TYPES.includes(meal.meal_type as MealType) ? meal.meal_type : "Snack";
      map.get(key)?.push(meal);
    }
    return map;
  }, [day]);

  const starredDays = useMemo(
    () => new Set((monthData?.days || []).filter((item) => item.hit_goal).map((item) => item.date)),
    [monthData],
  );
  const calendarCells = useMemo(() => buildMonthGrid(calendarMonth), [calendarMonth]);

  const resetForm = () => {
    estimateSeq.current += 1;
    setName("");
    setCalories("");
    setProtein("");
    setCarbs("");
    setFat("");
    setFiber("");
    setEstimateSource(null);
    setEstimating(false);
  };

  const refresh = async () => {
    await load();
    await loadMonth(monthKeyFromDate(date));
  };

  const onLog = async (event: FormEvent) => {
    event.preventDefault();
    const food = name.trim();
    if (!food) return;
    setBusy(true);
    setError(null);
    try {
      let nextCalories = calories;
      let nextProtein = protein;
      let nextCarbs = carbs;
      let nextFat = fat;
      let nextFiber = fiber;
      if (!nextCalories) {
        const estimate = await api.estimateMeal(food);
        nextCalories = String(Math.round(estimate.calories));
        nextProtein = grams(estimate.protein);
        nextCarbs = grams(estimate.carbs);
        nextFat = grams(estimate.fat);
        nextFiber = grams(estimate.fiber);
        setCalories(nextCalories);
        setProtein(nextProtein);
        setCarbs(nextCarbs);
        setFat(nextFat);
        setFiber(nextFiber);
      }
      await api.createMeal({
        name: food,
        meal_type: mealType,
        calories: Number(nextCalories),
        protein: nextProtein ? Number(nextProtein) : null,
        carbs: nextCarbs ? Number(nextCarbs) : null,
        fat: nextFat ? Number(nextFat) : null,
        fiber: nextFiber ? Number(nextFiber) : null,
        eaten_at: `${date}T12:00:00+05:30`,
      });
      setMessage(`Logged ${food}`);
      setOpenType(mealType);
      resetForm();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log meal");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: number) => {
    setBusy(true);
    try {
      await api.deleteMeal(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete meal");
    } finally {
      setBusy(false);
    }
  };

  const onGoal = async () => {
    const next = Number(goalDraft);
    if (!next) return;
    setBusy(true);
    try {
      const prot = Number(proteinGoalDraft) || undefined;
      await api.setDietGoal(next, prot);
      await refresh();
      setMessage("Goals saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save goal");
    } finally {
      setBusy(false);
    }
  };

  const onAddWater = async (addMl: number) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.addDietWater(addMl, date);
      setDay((prev) =>
        prev
          ? {
              ...prev,
              water_ml: result.water_ml,
              water_goal_ml: result.water_goal_ml,
              water_remaining_ml: result.water_remaining_ml,
              hydrated: result.hydrated,
            }
          : prev,
      );
      await loadMonth(monthKeyFromDate(date));
      setMessage(result.hydrated ? "Hydrated for today" : `+${addMl} ml water`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log water");
    } finally {
      setBusy(false);
    }
  };

  const eaten = day?.calories ?? 0;
  const goal = day?.calorie_goal || 2200;
  const proteinEaten = day?.protein ?? 0;
  const proteinGoal = day?.protein_goal || 120;
  const waterMl = day?.water_ml ?? 0;
  const waterGoalMl = day?.water_goal_ml || 3000;
  const hydrated = Boolean(day?.hydrated) || waterMl >= waterGoalMl;
  const calorieFill = Math.min(100, Math.round((eaten / goal) * 100));
  const proteinFill = Math.min(100, Math.round((proteinEaten / proteinGoal) * 100));
  const waterFill = Math.min(100, Math.round((waterMl / waterGoalMl) * 100));
  const calorieOver = eaten > goal;
  const proteinOver = proteinEaten > proteinGoal;
  const streak = monthData?.streak_days ?? 0;
  const graceMisses = monthData?.grace_misses ?? 0;
  const estimateChip = calories
    ? `${Math.round(Number(calories) || 0)} kcal${protein ? ` · ${protein}g P` : ""}`
    : null;

  return (
    <section className="section diet-page">
      <div className="diet-top">
        <div>
          <h2>Diet</h2>
          <p className="lede">Log food & water. Track goals. Keep the streak.</p>
        </div>
        <button
          type="button"
          className="diet-streak"
          onClick={() => setCalendarOpen(true)}
          title={
            graceMisses > 0
              ? `On grace — ${graceMisses} miss day${graceMisses === 1 ? "" : "s"} (breaks after 2)`
              : "Open calendar"
          }
        >
          <span aria-hidden="true">★</span>
          <b>{streak}</b>
          <span>streak</span>
        </button>
      </div>

      <div className={`diet-toolbar${calendarOpen ? " is-open" : ""}`}>
        <button type="button" className="diet-nav" onClick={() => setDate(shiftDate(date, -1))} aria-label="Previous day">
          ‹
        </button>
        <button type="button" className="diet-date" onClick={() => setCalendarOpen((open) => !open)}>
          <span>{prettyDate(date)}</span>
          <CalendarIcon />
        </button>
        <button
          type="button"
          className="diet-nav"
          onClick={() => setDate(shiftDate(date, 1))}
          disabled={date === today}
          aria-label="Next day"
        >
          ›
        </button>
      </div>

      {calendarOpen && (
        <div className="diet-calendar">
          <div className="diet-calendar-head">
            <button
              type="button"
              className="diet-nav"
              onClick={() => {
                const [y, m] = calendarMonth.split("-").map(Number);
                const prev = new Date(Date.UTC(y, m - 2, 1));
                setCalendarMonth(`${prev.getUTCFullYear()}-${String(prev.getUTCMonth() + 1).padStart(2, "0")}`);
              }}
              aria-label="Previous month"
            >
              ‹
            </button>
            <strong>{monthTitle(calendarMonth)}</strong>
            <button
              type="button"
              className="diet-nav"
              onClick={() => {
                const [y, m] = calendarMonth.split("-").map(Number);
                const next = new Date(Date.UTC(y, m, 1));
                setCalendarMonth(`${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, "0")}`);
              }}
              aria-label="Next month"
            >
              ›
            </button>
          </div>
          <div className="diet-calendar-weekdays">
            {["S", "M", "T", "W", "T", "F", "S"].map((label, i) => (
              <span key={`${label}-${i}`}>{label}</span>
            ))}
          </div>
          <div className="diet-calendar-grid">
            {calendarCells.map((cell, index) => {
              if (!cell) return <span key={`blank-${index}`} className="diet-calendar-blank" />;
              const isActive = cell === date;
              const isToday = cell === today;
              const hitGoal = starredDays.has(cell);
              return (
                <button
                  key={cell}
                  type="button"
                  className={`diet-calendar-day${isActive ? " is-active" : ""}${isToday ? " is-today" : ""}${hitGoal ? " is-hit" : ""}`}
                  onClick={() => {
                    setDate(cell);
                    setCalendarOpen(false);
                  }}
                >
                  <span>{Number(cell.slice(-2))}</span>
                  {hitGoal && <i>★</i>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {date !== today && (
        <button type="button" className="text-link" onClick={() => setDate(today)}>
          Jump to today
        </button>
      )}

      {error && <p className="error">{error}</p>}
      {message && <p className="ok">{message}</p>}

      {pageLoading ? (
        <CookingLoader />
      ) : (
      <>
      <div className="diet-snapshot">
        <div className="diet-progress">
          <article className={`diet-card${calorieOver ? " is-over" : ""}`}>
            <span className="diet-card-kicker">Calories</span>
            <strong>{Math.round(eaten).toLocaleString("en-IN")}</strong>
            <span className="diet-card-meta">
              {calorieOver ? `${kcal(eaten - goal)} over` : `${kcal(day?.remaining ?? goal)} left`}
            </span>
            <div className="diet-bar" aria-hidden="true">
              <span style={{ width: `${calorieFill}%` }} />
            </div>
          </article>
          <article className={`diet-card${proteinOver ? " is-over" : ""}`}>
            <span className="diet-card-kicker">Protein</span>
            <strong>{grams(proteinEaten)} g</strong>
            <span className="diet-card-meta">
              {proteinOver
                ? `${grams(Math.abs(day?.protein_remaining ?? 0))} g over`
                : `${grams(day?.protein_remaining ?? proteinGoal)} g left`}
            </span>
            <div className="diet-bar" aria-hidden="true">
              <span style={{ width: `${proteinFill}%` }} />
            </div>
          </article>
        </div>
        <article className={`diet-card diet-water-card${hydrated ? " is-hydrated" : ""}`}>
          <div className="diet-water-top">
            <div>
              <span className="diet-card-kicker">Water</span>
              <strong>
                {liters(waterMl)} L
                <span className="diet-water-goal"> / {liters(waterGoalMl)} L</span>
              </strong>
              <span className="diet-card-meta">
                {hydrated
                  ? "Hydrated"
                  : `${liters(Math.max(0, waterGoalMl - waterMl))} L left`}
              </span>
            </div>
            <div className="diet-water-actions">
              {[250, 500, 1000].map((ml) => (
                <button
                  key={ml}
                  type="button"
                  className="diet-water-add"
                  disabled={busy}
                  onClick={() => void onAddWater(ml)}
                >
                  +{ml >= 1000 ? "1 L" : `${ml} ml`}
                </button>
              ))}
            </div>
          </div>
          <div className="diet-bar diet-water-bar" aria-hidden="true">
            <span style={{ width: `${waterFill}%` }} />
          </div>
        </article>
        <div className="diet-macros">
          <div>
            <span>Carbs</span>
            <b>{grams(day?.carbs ?? 0)} g</b>
          </div>
          <div>
            <span>Fat</span>
            <b>{grams(day?.fat ?? 0)} g</b>
          </div>
          <div>
            <span>Fiber</span>
            <b>{grams(day?.fiber ?? 0)} g</b>
          </div>
        </div>
        <button type="button" className="diet-goals-toggle" onClick={() => setGoalsOpen((open) => !open)}>
          {goalsOpen ? "Hide goals" : "Edit calorie & protein goals"}
        </button>
        {goalsOpen && (
          <div className="diet-goals-inline">
            <label className="diet-macro-field" htmlFor="calorie-goal">
              <span>Calories</span>
              <input
                id="calorie-goal"
                className="input"
                inputMode="numeric"
                value={goalDraft}
                onChange={(e) => setGoalDraft(e.target.value)}
              />
            </label>
            <label className="diet-macro-field" htmlFor="protein-goal">
              <span>Protein</span>
              <input
                id="protein-goal"
                className="input"
                inputMode="numeric"
                value={proteinGoalDraft}
                onChange={(e) => setProteinGoalDraft(e.target.value)}
                placeholder="120"
              />
            </label>
            <button className="btn btn-ghost diet-save" type="button" disabled={busy} onClick={() => void onGoal()}>
              Save
            </button>
          </div>
        )}
      </div>

      <form className="diet-log" onSubmit={onLog}>
        <div className="diet-log-head">
          <h3>Log a meal</h3>
          <p className="muted diet-estimate-status">
            {estimating
              ? "Estimating…"
              : estimateSource
                ? estimateSource === "memory"
                  ? "From your past log"
                  : estimateSource === "branded"
                    ? "From product label"
                    : "Estimated for this amount"
                : "Type the food and amount"}
          </p>
        </div>
        <div className="diet-types">
          {MEAL_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              className={`diet-type${mealType === type ? " is-on" : ""}`}
              onClick={() => setMealType(type)}
            >
              {type}
            </button>
          ))}
        </div>
        <input
          className="input diet-food"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setCalories("");
            setProtein("");
            setCarbs("");
            setFat("");
            setFiber("");
            setEstimateSource(null);
          }}
          placeholder="Avocado (half), 2 eggs"
          autoComplete="off"
        />
        {(estimateChip || name.trim().length >= 3) && (
          <button type="button" className="diet-estimate-chip" onClick={() => setAdjustOpen((open) => !open)}>
            {estimating ? "Estimating…" : estimateChip || "Adjust macros"}
            <span>{adjustOpen ? "Hide" : "Edit"}</span>
          </button>
        )}
        {adjustOpen && (
          <div className="diet-macro-row">
            <label className="diet-macro-field">
              <span>Cal</span>
              <input className="input" inputMode="decimal" value={calories} onChange={(e) => setCalories(e.target.value)} readOnly={estimating} />
            </label>
            <label className="diet-macro-field">
              <span>Protein</span>
              <input className="input" inputMode="decimal" value={protein} onChange={(e) => setProtein(e.target.value)} readOnly={estimating} />
            </label>
            <label className="diet-macro-field">
              <span>Carbs</span>
              <input className="input" inputMode="decimal" value={carbs} onChange={(e) => setCarbs(e.target.value)} readOnly={estimating} />
            </label>
            <label className="diet-macro-field">
              <span>Fat</span>
              <input className="input" inputMode="decimal" value={fat} onChange={(e) => setFat(e.target.value)} readOnly={estimating} />
            </label>
            <label className="diet-macro-field">
              <span>Fiber</span>
              <input className="input" inputMode="decimal" value={fiber} onChange={(e) => setFiber(e.target.value)} readOnly={estimating} />
            </label>
          </div>
        )}
        <button className="btn btn-primary diet-log-btn" type="submit" disabled={busy || estimating || !name.trim()}>
          {estimating ? "Estimating…" : "Log meal"}
        </button>
      </form>

      <div className="diet-board">
        {MEAL_TYPES.map((type) => {
          const meals = grouped.get(type) || [];
          const total = meals.reduce((sum, meal) => sum + meal.calories, 0);
          const open = openType === type;
          return (
            <div key={type} className={`diet-row${open ? " is-open" : ""}`}>
              <button type="button" className="diet-row-toggle" onClick={() => setOpenType(open ? null : type)}>
                <span>
                  <b>{type}</b>
                  <small>{meals.length} item{meals.length === 1 ? "" : "s"}</small>
                </span>
                <strong>{kcal(total)}</strong>
              </button>
              {open && (
                <div className="diet-row-body">
                  {meals.length === 0 && <p className="muted empty-state">Nothing logged yet.</p>}
                  {meals.map((meal) => (
                    <div key={meal.id} className="diet-meal">
                      <div>
                        <div className="payment-label">{meal.name}</div>
                        <div className="muted diet-meal-meta">
                          {kcal(meal.calories)}
                          {meal.protein != null ? ` · P ${grams(meal.protein)}` : ""}
                          {meal.carbs != null ? ` · C ${grams(meal.carbs)}` : ""}
                          {meal.fat != null ? ` · F ${grams(meal.fat)}` : ""}
                          {meal.fiber != null ? ` · Fiber ${grams(meal.fiber)}` : ""}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="icon-delete"
                        aria-label={`Delete ${meal.name}`}
                        title="Delete"
                        onClick={() => void onDelete(meal.id)}
                        disabled={busy}
                      >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                          <path
                            fill="currentColor"
                            d="M9 3h6l1 2h4v2H4V5h4zm1 6h2v9h-2zm4 0h2v9h-2zM7 8h10l-.8 11.1A2 2 0 0 1 14.21 21H9.79a2 2 0 0 1-1.99-1.9z"
                          />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      </>
      )}
    </section>
  );
}
