"use client";

/** Tell the NUTRIFIN splash the first screen is ready to show. */
export function signalNutrifinReady() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("nutrifin-ready"));
}
