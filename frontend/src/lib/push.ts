"use client";

// Web Push helpers for staff devices. The browser subscription is created
// locally (VAPID public key from the API) and persisted server-side per user
// so order/booking events can reach this device.

import { api } from "@/lib/api";

export type PushConfig = { enabled: boolean; public_key: string | null };

export type PushSubscriptionRow = {
  id: string;
  endpoint: string;
  user_agent: string | null;
  created_at: string;
};

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const normalized = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(normalized);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

export async function currentDeviceEndpoint(): Promise<string | null> {
  if (!pushSupported()) return null;
  const registration = await navigator.serviceWorker.getRegistration();
  if (!registration) return null;
  const subscription = await registration.pushManager.getSubscription();
  return subscription?.endpoint ?? null;
}

export async function subscribeCurrentDevice(publicKey: string): Promise<void> {
  const registration = await navigator.serviceWorker.ready;
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Notifications are blocked for this site in your browser settings");
  }
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  });
  const json = subscription.toJSON() as {
    endpoint?: string;
    keys?: { p256dh?: string; auth?: string };
  };
  if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) {
    throw new Error("The browser did not return a usable push subscription");
  }
  await api("/push/subscriptions", {
    body: {
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
      user_agent: navigator.userAgent.slice(0, 255),
    },
  });
}

export async function removePushSubscription(row: PushSubscriptionRow): Promise<void> {
  const endpoint = await currentDeviceEndpoint();
  if (endpoint && endpoint === row.endpoint) {
    const registration = await navigator.serviceWorker.getRegistration();
    const subscription = await registration?.pushManager.getSubscription();
    await subscription?.unsubscribe().catch(() => undefined);
  }
  await api(`/push/subscriptions/${row.id}`, { method: "DELETE" });
}
