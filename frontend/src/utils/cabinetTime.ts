/** Отображение дат/времени в кабинете: Europe/Moscow (UTC+3, без перехода на летнее). */

const MSK: Intl.DateTimeFormatOptions = {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
};

/**
 * Бэкенд/SQLite часто отдаёт ISO без зоны (2024-01-15T12:00:00).
 * В JS это трактуется как *локальное* время браузера → в часовом поясе МСК сдвиг на −3 ч к UTC.
 * Считаем такие значения UTC и дописываем Z.
 */
function parseApiDate(input: string): Date {
  const s = input.trim();
  if (!s) return new Date(NaN);
  if (/[zZ]$/.test(s)) return new Date(s);
  if (/[+-]\d{2}:\d{2}$/.test(s)) return new Date(s);

  let norm = s.includes("T") ? s : s.replace(/^(\d{4}-\d{2}-\d{2})\s+/, "$1T");

  if (/^\d{4}-\d{2}-\d{2}$/.test(norm)) {
    return new Date(`${norm}T00:00:00Z`);
  }

  if (/^\d{4}-\d{2}-\d{2}T/.test(norm)) {
    const dot = norm.indexOf(".");
    if (dot !== -1) {
      norm = norm.slice(0, Math.min(dot + 4, norm.length));
    }
    return new Date(`${norm}Z`);
  }

  return new Date(s);
}

export function formatDateTimeMsk(input: string | Date | null | undefined): string {
  if (input == null || input === "") return "—";
  const d = input instanceof Date ? input : parseApiDate(input);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toLocaleString("ru-RU", MSK)} МСК`;
}
