"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

function isReload() {
  const entries = performance.getEntriesByType("navigation");
  const nav = entries[0] as PerformanceNavigationTiming | undefined;
  if (nav?.type) return nav.type === "reload";
  return (performance as unknown as { navigation?: { type?: number } }).navigation?.type === 1;
}

export default function AppSessionHome() {
  const pathname = usePathname();

  useEffect(() => {
    if (pathname === "/" || pathname === "/chat") return;
    if (!isReload()) return;
    window.location.replace("/");
  }, [pathname]);

  return null;
}
