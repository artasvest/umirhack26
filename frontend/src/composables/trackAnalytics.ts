import { api } from "@/api/client";

export async function trackEvent(
  sessionId: string,
  eventType: string,
  stepKey?: string,
  payload?: Record<string, unknown>,
  quizSchemaId?: number | null,
): Promise<void> {
  try {
    const body: Record<string, unknown> = {
      session_id: sessionId,
      event_type: eventType,
      step_key: stepKey ?? null,
      payload: payload ?? null,
    };
    if (quizSchemaId != null && quizSchemaId > 0) {
      body.quiz_schema_id = quizSchemaId;
    }
    await api("/analytics/track", {
      method: "POST",
      json: body,
    });
  } catch {
    /* не блокируем квиз */
  }
}
