const TOKEN_KEY = "studio_jwt";
const USER_ID_KEY = "studio_user_id";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUserId(): string | null {
  return localStorage.getItem(USER_ID_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_ID_KEY);
  }
}

function clearAuthSession(): void {
  setToken(null);
  localStorage.removeItem("studio_role");
  localStorage.removeItem("studio_name");
}

export type LeadStatus = "pending" | "in_progress" | "completed";

export interface LeadPublic {
  id: string;
  request_number: string;
  status: LeadStatus;
  answers: Record<string, unknown>;
  ai_summary_client?: string | null;
  updated_at?: string | null;
}

export interface LeadReminder {
  id: string;
  remind_at: string;
  sent: boolean;
  manager_id: string;
  manager_name?: string | null;
}

export interface LeadManagerDetail {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  comment: string | null;
  consent: boolean;
  answers: Record<string, unknown>;
  ai_summary: string | null;
  ai_summary_client?: string | null;
  call_script: string | null;
  status: LeadStatus;
  assigned_manager_id: string | null;
  created_at: string;
  updated_at: string | null;
  pool_entered_at?: string | null;
  callback_at?: string | null;
  callback_note?: string | null;
  page_url?: string | null;
  utm_source?: string | null;
  notes: NoteOut[];
  reminders?: LeadReminder[];
  request_number: string;
}

export interface NoteOut {
  id: string;
  body: string;
  is_voice: boolean;
  created_at: string;
  author_id: string | null;
}

export interface LeadListItem {
  id: string;
  name: string;
  phone: string;
  room_type: string | null;
  budget: string | null;
  status: LeadStatus;
  created_at: string;
  assigned_manager_id?: string | null;
  assigned_manager_name?: string | null;
  pool_entered_at?: string | null;
  callback_at?: string | null;
  callback_note?: string | null;
}

const HTTP_STATUS_RU: Record<number, string> = {
  400: "Некорректный запрос",
  401: "Нужно войти в систему",
  403: "Недостаточно прав",
  404: "Ничего не найдено",
  409: "Действие сейчас невозможно (данные могли измениться)",
  413: "Слишком большой файл",
  422: "Проверьте поля формы",
  429: "Слишком много запросов, подождите",
  500: "Ошибка на сервере",
  502: "Сервер временно недоступен",
  503: "Сервис временно недоступен",
};

function humanizeDetailArray(detail: unknown[]): string {
  const parts: string[] = [];
  for (const item of detail) {
    if (typeof item === "string") {
      parts.push(item);
      continue;
    }
    if (item && typeof item === "object" && "msg" in item) {
      const m = (item as { msg?: string }).msg;
      if (typeof m === "string") {
        let s = m;
        if (s.startsWith("Value error, ")) s = s.slice("Value error, ".length).trim();
        parts.push(s);
      }
    }
  }
  return parts.filter(Boolean).join(". ") || "Проверьте введённые данные.";
}

async function parseError(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as { detail?: unknown };
    if (j && typeof j.detail === "string") return j.detail;
    if (j && Array.isArray(j.detail)) return humanizeDetailArray(j.detail);
  } catch {
    /* ignore */
  }
  const ru = HTTP_STATUS_RU[res.status];
  if (ru) return ru;
  const en = (res.statusText || "").trim();
  if (en && en !== "OK") return en;
  return "Не удалось выполнить запрос. Попробуйте ещё раз.";
}

export async function api<T>(
  path: string,
  opts: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, ...init } = opts;
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }
  const p = path.startsWith("/") ? path : `/${path}`;
  const res = await fetch(`/api${p}`, { ...init, headers, body });

  if (res.status === 401) {
    const errText = await parseError(res);
    if (p !== "/auth/login") {
      clearAuthSession();
      const here = `${window.location.pathname}${window.location.search}`;
      const blocked = errText.includes("заблокирован");
      window.location.assign(
        blocked ? "/login?blocked=1" : `/login?redirect=${encodeURIComponent(here)}`,
      );
    }
    throw new Error(errText);
  }

  if (!res.ok) throw new Error(await parseError(res));
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as T;
}

export async function loginRequest(email: string, password: string) {
  return api<{ access_token: string; role: string; full_name: string; user_id: string }>("/auth/login", {
    method: "POST",
    json: { email, password },
  });
}

export async function requestTelegramLink() {
  return api<{ url: string; expires_at: string }>("/auth/telegram-link", { method: "POST" });
}

export function statusLabelRu(s: LeadStatus): string {
  switch (s) {
    case "pending":
      return "Ожидает";
    case "in_progress":
      return "В обработке";
    case "completed":
      return "Завершена";
    default:
      return s;
  }
}
