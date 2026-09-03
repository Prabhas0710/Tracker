self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let payload = { title: "Ledgerly", body: "A new payment needs a category.", url: "/expenses" };
  try {
    payload = { ...payload, ...(event.data ? event.data.json() : {}) };
  } catch {
    /* ignore */
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || "Ledgerly", {
      body: payload.body || "A new payment needs a category.",
      tag: "ledgerly-payment",
      renotify: true,
      data: {
        url: payload.url || "/expenses",
        clarification_id: payload.clarification_id || null,
      },
      actions: [
        { action: "Food", title: "Food" },
        { action: "Entertainment", title: "Entertainment" },
        { action: "Personal", title: "Personal" },
      ],
    }),
  );
});

async function saveFromNotification(clarificationId, text) {
  const res = await fetch("/api/voice/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clarification_id: Number(clarificationId), text }),
  });
  if (!res.ok) throw new Error("save failed");
  return res.json();
}

self.addEventListener("notificationclick", (event) => {
  const picked = event.action;
  const data = event.notification.data || {};
  event.notification.close();

  if (picked && data.clarification_id) {
    event.waitUntil(
      saveFromNotification(data.clarification_id, picked)
        .then((result) => {
          const body = result.matched
            ? `Saved as ${result.category}.`
            : "Could not save. Open Ledgerly to type a category.";
          return self.registration.showNotification("Ledgerly", {
            body,
            tag: "ledgerly-saved",
          });
        })
        .catch(() =>
          self.registration.showNotification("Ledgerly", {
            body: "Could not save. Open Ledgerly to pick a category.",
            tag: "ledgerly-saved",
          }),
        ),
    );
    return;
  }

  const base = data.url || "/expenses";
  const cid = data.clarification_id ? `&cid=${encodeURIComponent(String(data.clarification_id))}` : "";
  const joiner = base.includes("?") ? "&" : "?";
  const target = `${base}${joiner}ask=1${cid}`.replace(/ask=1&ask=1/, "ask=1");
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ("focus" in client) {
          client.navigate?.(target);
          return client.focus();
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(target);
      return undefined;
    }),
  );
});
