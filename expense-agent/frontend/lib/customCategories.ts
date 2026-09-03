"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { isBuiltInCategory } from "@/lib/categories";

const STORAGE_KEY = "ledgerly-custom-categories";

function normalize(list: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of list) {
    const name = raw.trim();
    const key = name.toLowerCase();
    if (!name || isBuiltInCategory(name) || key === "credit card" || seen.has(key)) continue;
    seen.add(key);
    out.push(name);
  }
  return out;
}

function readStored(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? normalize(parsed.map(String)) : [];
  } catch {
    return [];
  }
}

let extras: string[] = [];
const listeners = new Set<() => void>();

function emit() {
  extras = normalize(extras);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(extras));
  }
  listeners.forEach((fn) => fn());
}

export function rememberCustomCategory(name: string) {
  const next = normalize([...extras, name]);
  if (next.length === extras.length && next.every((item, i) => item === extras[i])) return;
  extras = next;
  emit();
}

export function rememberCustomCategories(names: string[]) {
  const next = normalize([...extras, ...names]);
  if (next.length === extras.length && next.every((item, i) => item === extras[i])) return;
  extras = next;
  emit();
}

export function useCustomCategories(): string[] {
  const [list, setList] = useState<string[]>([]);

  useEffect(() => {
    extras = normalize([...readStored(), ...extras]);
    const onChange = () => setList([...extras]);
    listeners.add(onChange);
    onChange();
    api
      .getCategoryNames()
      .then((names) => rememberCustomCategories(names))
      .catch(() => {});
    return () => {
      listeners.delete(onChange);
    };
  }, []);

  return list;
}
