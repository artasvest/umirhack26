/** 10 цифр мобильного РФ без учётной семёрки (как в маске +7 …). */

export function extractRuMobileDigits(raw: string): string {
  let d = raw.replace(/\D/g, "");
  if (d.startsWith("8")) d = d.slice(1);
  if (d.startsWith("7")) d = d.slice(1);
  return d.slice(0, 10);
}

/** Отображение: +7 (XXX) XXX-XX-XX; незаполненный хвост не показываем. */
export function formatRuPhoneDisplay(digits10: string): string {
  const d = extractRuMobileDigits(digits10);
  if (d.length === 0) return "+7 (";
  let out = "+7 (";
  out += d.slice(0, Math.min(3, d.length));
  if (d.length <= 3) return out;
  out += ") " + d.slice(3, Math.min(6, d.length));
  if (d.length <= 6) return out;
  out += "-" + d.slice(6, Math.min(8, d.length));
  if (d.length <= 8) return out;
  out += "-" + d.slice(8, 10);
  return out;
}

export function isRuPhoneComplete(digits10: string): boolean {
  return extractRuMobileDigits(digits10).length === 10;
}

/** Для API: +7XXXXXXXXXX */
export function ruPhoneToE164(digits10: string): string {
  const d = extractRuMobileDigits(digits10);
  return `+7${d}`;
}
