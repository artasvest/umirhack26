import { api } from "@/api/client";

export async function trackEvent(
  sessionId: string,
  eventType: string,
  stepKey?: string,
  payload?: Record<string, unknown>,
): Promise<void> {
  try {
    await api("/analytics/track", {
      method: "POST",
      json: {
        session_id: sessionId,
        event_type: eventType,
        step_key: stepKey ?? null,
        payload: payload ?? null,
      },
    });
  } catch {
    /* не блокируем квиз */
  }
}
