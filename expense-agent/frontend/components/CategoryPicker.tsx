"use client";

import { useMemo } from "react";
import { ALL_CATEGORIES, SPEND_CATEGORIES, mergeCategoryOptions } from "@/lib/categories";
import { rememberCustomCategory, useCustomCategories } from "@/lib/customCategories";

type Props = {
  current?: string | null;
  includeIncome?: boolean;
  disabled?: boolean;
  extraCategories?: string[];
  onSelect: (category: string) => void;
};

export function CategoryPicker({
  current,
  includeIncome = false,
  disabled = false,
  extraCategories,
  onSelect,
}: Props) {
  const stored = useCustomCategories();
  const options = useMemo(
    () =>
      mergeCategoryOptions(
        includeIncome ? ALL_CATEGORIES : SPEND_CATEGORIES,
        [...stored, ...(extraCategories || [])],
        current,
      ),
    [current, extraCategories, includeIncome, stored],
  );

  return (
    <div className="category-picker" role="listbox" aria-label="Choose category">
      {options.map((category) => {
        const active = (current || "").toLowerCase() === category.toLowerCase();
        return (
          <button
            key={category}
            type="button"
            role="option"
            aria-selected={active}
            className={`category-chip${active ? " active" : ""}`}
            disabled={disabled}
            onClick={() => {
              rememberCustomCategory(category);
              onSelect(category);
            }}
          >
            {category}
          </button>
        );
      })}
    </div>
  );
}
