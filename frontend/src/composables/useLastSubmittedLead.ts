const STORAGE_KEY = "studio_last_lead_v1";

export interface LastSubmittedLead {
  id: string;
  requestNumber: string;
  submittedAt: string;
}

export function loadLastSubmittedLead(): LastSubmittedLead | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw) as Partial<LastSubmittedLead>;
    if (!o.id || typeof o.id !== "string") return null;
    if (!o.requestNumber || typeof o.requestNumber !== "string") return null;
    return {
      id: o.id,
      requestNumber: o.requestNumber,
      submittedAt: typeof o.submittedAt === "string" ? o.submittedAt : "",
    };
  } catch {
    return null;
  }
}

/** Сохраняется отдельно от прогресса квиза — не трогается при clearPersisted. */
export function saveLastSubmittedLead(id: string, requestNumber: string): void {
  const payload: LastSubmittedLead = {
    id,
    requestNumber,
    submittedAt: new Date().toISOString(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function clearLastSubmittedLead(): void {
  localStorage.removeItem(STORAGE_KEY);
}
