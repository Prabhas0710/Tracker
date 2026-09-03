"use client";

import { usePathname } from "next/navigation";
import type { MouseEvent } from "react";

const tabs = [
  { href: "/", label: "Chat" },
  { href: "/diet", label: "Diet" },
  { href: "/expenses", label: "Expenses" },
  { href: "/analytics", label: "Analytics" },
  { href: "/history", label: "History" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/" || pathname === "/chat";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function openPage(event: MouseEvent<HTMLAnchorElement>, href: string) {
  event.preventDefault();
  event.stopPropagation();
  window.location.assign(href);
}

export default function TopTabs() {
  const pathname = usePathname();

  return (
    <nav className="top-tabs" aria-label="Main">
      {tabs.map((tab) => (
        <a
          key={tab.href}
          href={tab.href}
          className={`top-tab${isActive(pathname, tab.href) ? " is-active" : ""}`}
          onClick={(event) => openPage(event, tab.href)}
        >
          {tab.label}
        </a>
      ))}
    </nav>
  );
}
