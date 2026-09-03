const ALERTS_KEY = "ledgerly-alerts-on";

function urlBase64ToUint8Array(base64: string) {
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

export function isStandaloneApp() {
  if (typeof window === "undefined") return false;
  const nav = window.navigator as Navigator & { standalone?: boolean };
  return window.matchMedia("(display-mode: standalone)").matches || Boolean(nav.standalone);
}

export async function enablePaymentAlerts(): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;
  if (typeof Notification === "undefined") return false;
  const permission =
    Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
  if (permission !== "granted") return false;
  return subscribePush();
}

export async function subscribeIfPermitted(): Promise<boolean> {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return false;
  return subscribePush();
}

async function subscribePush(): Promise<boolean> {

  const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  await navigator.serviceWorker.ready;

  const keyRes = await fetch("/api/voice/push-key");
  if (!keyRes.ok) return false;
  const { publicKey } = (await keyRes.json()) as { publicKey?: string };
  if (!publicKey) return false;

  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
  }

  const res = await fetch("/api/voice/push-subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription.toJSON()),
  });
  if (!res.ok) return false;
  localStorage.setItem(ALERTS_KEY, "1");
  try {
    new Notification("Ledgerly", {
      body: "Alerts are on. You will get a ping after each payment.",
      tag: "ledgerly-alerts-on",
    });
  } catch {
    /* ignore */
  }
  return true;
}

export function alertsEnabled() {
  try {
    return localStorage.getItem(ALERTS_KEY) === "1";
  } catch {
    return false;
  }
}
