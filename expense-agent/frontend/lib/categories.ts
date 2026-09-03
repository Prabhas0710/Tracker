/** Spend categories shown in the picker (Income is set automatically for credits). */
export const SPEND_CATEGORIES = [
  "Food",
  "Groceries",
  "Entertainment",
  "Fuel",
  "Transport",
  "Shopping",
  "Bills",
  "Recharge",
  "Health",
  "Transfer",
  "Self Transfer",
  "Personal",
  "Other",
] as const;

export const ALL_CATEGORIES = ["Income", ...SPEND_CATEGORIES] as const;

export type SpendCategory = (typeof SPEND_CATEGORIES)[number];

export const SELF_TRANSFER_LABEL = "Self Transfer";

const HIDDEN_CATEGORIES = new Set(["credit card", "needs you"]);

const BUILT_IN_LOOKUP = new Set(
  ["Income", ...SPEND_CATEGORIES].map((name) => name.toLowerCase()),
);

export function isBuiltInCategory(name: string): boolean {
  return BUILT_IN_LOOKUP.has(name.trim().toLowerCase());
}

export function mergeCategoryOptions(
  base: readonly string[],
  extras: string[],
  current?: string | null,
): string[] {
  const seen = new Set<string>();
  const custom: string[] = [];
  const rest: string[] = [];
  const other: string[] = [];

  const push = (name: string, bucket: string[]) => {
    const trimmed = name.trim();
    const key = trimmed.toLowerCase();
    if (!trimmed || seen.has(key) || HIDDEN_CATEGORIES.has(key)) return;
    seen.add(key);
    bucket.push(trimmed);
  };

  for (const name of extras) {
    if (!isBuiltInCategory(name)) push(name, custom);
  }
  if (current && !isBuiltInCategory(current)) push(current, custom);
  for (const name of base) {
    if (name === "Other") push(name, other);
    else push(name, rest);
  }
  return [...rest, ...custom, ...other];
}

/** Stable display name: Recharge stays Recharge, not "recharge". */
export function displayCategoryName(name: string): string {
  const trimmed = (name || "").trim();
  if (!trimmed) return "Other";
  const lower = trimmed.toLowerCase();
  if (lower === "needs you") return "Needs review";
  const known = [...ALL_CATEGORIES, SELF_TRANSFER_LABEL, "Credits"].find(
    (item) => item.toLowerCase() === lower,
  );
  if (known) return known;
  return trimmed.replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
}

/** Label shown in the category picker for an expense row. */
export function expenseCategoryLabel(expense: {
  category: string;
  direction?: string | null;
}): string {
  if ((expense.direction || "debit") === "transfer") return SELF_TRANSFER_LABEL;
  return displayCategoryName(expense.category);
}

export type CategorySelectionPayload = {
  category: string;
  subcategory: string | null;
  direction: "debit" | "credit" | "transfer";
};

/** Map a picker label (chip or custom text) to API fields. */
export function categorySelectionPayload(label: string): CategorySelectionPayload {
  const trimmed = label.trim();
  if (trimmed === SELF_TRANSFER_LABEL) {
    return { category: "Transfer", subcategory: "Self", direction: "transfer" };
  }
  if (trimmed === "Other") {
    return { category: "Other", subcategory: "Unknown", direction: "debit" };
  }
  if (trimmed === "Transfer") {
    return { category: "Transfer", subcategory: null, direction: "debit" };
  }
  if (trimmed === "Income") {
    return { category: "Income", subcategory: null, direction: "credit" };
  }
  return { category: trimmed, subcategory: null, direction: "debit" };
}

export function sameCategorySelection(
  expense: { category: string; subcategory?: string | null; direction?: string | null },
  payload: CategorySelectionPayload,
): boolean {
  return (
    expense.category === payload.category &&
    (expense.subcategory ?? null) === payload.subcategory &&
    (expense.direction || "debit") === payload.direction
  );
}
