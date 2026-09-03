"use client";

import { FormEvent, useMemo, useState } from "react";
import { ALL_CATEGORIES, SPEND_CATEGORIES, mergeCategoryOptions } from "@/lib/categories";
import { rememberCustomCategory, useCustomCategories } from "@/lib/customCategories";

const CUSTOM_VALUE = "__custom__";

type Props = {
  current?: string | null;
  includeIncome?: boolean;
  disabled?: boolean;
  onSelect: (category: string) => void;
};

export function CategoryEditor({
  current,
  includeIncome = false,
  disabled = false,
  onSelect,
}: Props) {
  const [custom, setCustom] = useState("");
  const [showCustom, setShowCustom] = useState(false);
  const extras = useCustomCategories();

  const options = useMemo(
    () =>
      mergeCategoryOptions(
        includeIncome ? ALL_CATEGORIES : SPEND_CATEGORIES,
        extras,
        current,
      ),
    [current, extras, includeIncome],
  );

  const selected = showCustom ? CUSTOM_VALUE : current || "";

  const onDropdownChange = (value: string) => {
    if (value === CUSTOM_VALUE) {
      setShowCustom(true);
      return;
    }
    setShowCustom(false);
    setCustom("");
    if (value && value !== current) onSelect(value);
  };

  const applyCustom = (e: FormEvent) => {
    e.preventDefault();
    const value = custom.trim();
    if (!value || disabled) return;
    rememberCustomCategory(value);
    onSelect(value);
    setCustom("");
    setShowCustom(false);
  };

  return (
    <div className="category-editor">
      <select
        className="month-select category-select"
        aria-label="Choose category"
        value={selected}
        disabled={disabled}
        onChange={(e) => onDropdownChange(e.target.value)}
      >
        {!current && <option value="">Select a category</option>}
        {options.map((category) => (
          <option key={category} value={category}>
            {category}
          </option>
        ))}
        <option value={CUSTOM_VALUE}>Type a new category…</option>
      </select>
      {showCustom && (
        <form className="category-custom-row" onSubmit={applyCustom}>
          <input
            className="input category-custom-input"
            type="text"
            placeholder="Type a new category"
            value={custom}
            disabled={disabled}
            autoFocus
            onChange={(e) => setCustom(e.target.value)}
            maxLength={80}
          />
          <button className="btn btn-ghost" type="submit" disabled={disabled || !custom.trim()}>
            Apply
          </button>
        </form>
      )}
    </div>
  );
}
