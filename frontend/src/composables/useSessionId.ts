const SID_KEY = "studio_quiz_session";

/** randomUUID только в secure context (HTTPS / localhost); на HTTP по IP — нет, см. MDN Crypto.randomUUID */
function randomUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    const b = new Uint8Array(16);
    crypto.getRandomValues(b);
    b[6] = (b[6]! & 0x0f) | 0x40;
    b[8] = (b[8]! & 0x3f) | 0x80;
    const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

export function useSessionId(): string {
  let id = sessionStorage.getItem(SID_KEY);
  if (!id) {
    id = randomUuid();
    sessionStorage.setItem(SID_KEY, id);
  }
  return id;
}

/** Новый id для воронки после завершённой заявки — иначе второй квиз в той же вкладке перезаписывает ответы в аналитике. */
export function rotateSessionId(): string {
  const id = randomUuid();
  sessionStorage.setItem(SID_KEY, id);
  return id;
}
