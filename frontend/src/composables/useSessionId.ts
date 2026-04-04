const SID_KEY = "studio_quiz_session";

export function useSessionId(): string {
  let id = sessionStorage.getItem(SID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SID_KEY, id);
  }
  return id;
}

/** Новый id для воронки после завершённой заявки — иначе второй квиз в той же вкладке перезаписывает ответы в аналитике. */
export function rotateSessionId(): string {
  const id = crypto.randomUUID();
  sessionStorage.setItem(SID_KEY, id);
  return id;
}
