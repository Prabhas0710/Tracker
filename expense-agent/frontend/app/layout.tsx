import type { Metadata, Viewport } from "next";
import { Fraunces, Manrope } from "next/font/google";
import { Suspense } from "react";
import AppSessionHome from "@/components/AppSessionHome";
import GmailStatusDot from "@/components/GmailStatusDot";
import ProfileButton from "@/components/ProfileButton";
import TopTabs from "@/components/TopTabs";
import "./globals.css";

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
});

const body = Manrope({
  subsets: ["latin"],
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "Ledgerly — Expense Agent",
  description: "Automatic payment understanding for everyday spending",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Ledgerly",
  },
  icons: {
    apple: "/icon.svg",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#03060c",
};

const themeBootScript = `
(() => {
  try {
    const theme = localStorage.getItem('ledgerly-theme');
    const next = theme === 'light' || theme === 'dark' ? theme : 'dark';
    document.documentElement.setAttribute('data-theme', next);
  } catch (_) {}
})();
`;

const homeOnRefreshScript = `
(() => {
  try {
    const path = location.pathname.replace(/\\/$/, '') || '/';
    if (path === '/' || path === '/chat') return;
    const nav = performance.getEntriesByType('navigation')[0];
    if (nav && nav.type === 'reload') location.replace('/');
  } catch (_) {}
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
        <script dangerouslySetInnerHTML={{ __html: homeOnRefreshScript }} />
      </head>
      <body suppressHydrationWarning>
        <Suspense fallback={null}>
          <AppSessionHome />
        </Suspense>
        <div className="app-shell">
          <header className="topbar">
            <div className="topbar-corner">
              <GmailStatusDot />
            </div>
            <TopTabs />
            <div className="topbar-corner topbar-corner-right">
              <ProfileButton />
            </div>
          </header>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
