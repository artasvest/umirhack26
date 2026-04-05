<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { api, statusLabelRu, type LeadManagerDetail, type LeadReminder } from "@/api/client";
import { formatDateTimeMsk } from "@/utils/cabinetTime";

const route = useRoute();
const id = computed(() => route.params.id as string);
const lead = ref<LeadManagerDetail | null>(null);
const error = ref("");
const noteText = ref("");
const reminderAt = ref("");
const callbackAtLocal = ref("");
const callbackNote = ref("");
const callbackBusy = ref(false);
const voiceBusy = ref(false);
const isRecording = ref(false);
const micRecorder = ref<MediaRecorder | null>(null);
const micStream = ref<MediaStream | null>(null);
const recordChunks = ref<BlobPart[]>([]);
const claimBusy = ref(false);
const reminderBusy = ref(false);

const sortedReminders = computed((): LeadReminder[] => {
  const raw = lead.value?.reminders;
  if (!raw?.length) return [];
  return [...raw].sort((a, b) => new Date(a.remind_at).getTime() - new Date(b.remind_at).getTime());
});

function preferredAudioMime(): string | undefined {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  for (const t of types) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) return t;
  }
  return undefined;
}

function stopMicTracks(): void {
  micStream.value?.getTracks().forEach((t) => t.stop());
  micStream.value = null;
}

async function uploadVoiceBlob(blob: Blob, filename: string): Promise<void> {
  voiceBusy.value = true;
  try {
    const fd = new FormData();
    fd.append("file", blob, filename);
    const token = localStorage.getItem("studio_jwt");
    const res = await fetch(`/api/leads/${id.value}/notes/voice`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    if (!res.ok) throw new Error(await res.text());
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Голосовая заметка не отправлена";
  } finally {
    voiceBusy.value = false;
  }
}

const isAdmin = computed(() => localStorage.getItem("studio_role") === "admin");
const myId = computed(() => localStorage.getItem("studio_user_id"));

const isPool = computed(
  () => !!lead.value && lead.value.status === "pending" && !lead.value.assigned_manager_id,
);
const isMineActive = computed(
  () =>
    !!lead.value &&
    lead.value.status === "in_progress" &&
    lead.value.assigned_manager_id === myId.value,
);
const isMineCompleted = computed(
  () =>
    !!lead.value &&
    lead.value.status === "completed" &&
    lead.value.assigned_manager_id === myId.value,
);
const canMutateNotes = computed(() => isAdmin.value || isMineActive.value || isMineCompleted.value);

async function load(): Promise<void> {
  try {
    lead.value = await api<LeadManagerDetail>(`/leads/${id.value}`);
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
  }
}

onMounted(() => void load());

onUnmounted(() => {
  if (micRecorder.value && micRecorder.value.state !== "inactive") {
    finishMicRecording(false);
  } else {
    stopMicTracks();
  }
});

function toDatetimeLocalValue(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

watch(
  lead,
  (l) => {
    if (!l) return;
    callbackNote.value = l.callback_note ?? "";
    callbackAtLocal.value = l.callback_at ? toDatetimeLocalValue(l.callback_at) : "";
  },
  { immediate: true },
);

async function claimLead(): Promise<void> {
  claimBusy.value = true;
  error.value = "";
  try {
    await api(`/leads/${id.value}/claim`, { method: "POST" });
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось взять заявку";
  } finally {
    claimBusy.value = false;
  }
}

async function releaseLead(): Promise<void> {
  if (!confirm("Вернуть заявку в общий пул? Её смогут взять другие менеджеры.")) return;
  error.value = "";
  try {
    await api(`/leads/${id.value}/release`, { method: "POST" });
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
  }
}

async function completeLead(): Promise<void> {
  error.value = "";
  try {
    await api(`/leads/${id.value}/status`, { method: "PATCH", json: { status: "completed" } });
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
  }
}

async function addNote(): Promise<void> {
  if (!noteText.value.trim()) return;
  await api(`/leads/${id.value}/notes`, { method: "POST", json: { text: noteText.value.trim() } });
  noteText.value = "";
  await load();
}

async function startMicRecording(): Promise<void> {
  error.value = "";
  if (!navigator.mediaDevices?.getUserMedia) {
    error.value = "Запись с микрофона недоступна в этом браузере";
    return;
  }
  if (isRecording.value || voiceBusy.value) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    micStream.value = stream;
    recordChunks.value = [];
    const mime = preferredAudioMime();
    const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    micRecorder.value = rec;
    rec.ondataavailable = (ev) => {
      if (ev.data.size > 0) recordChunks.value.push(ev.data);
    };
    rec.start(250);
    isRecording.value = true;
  } catch (e) {
    stopMicTracks();
    micRecorder.value = null;
    isRecording.value = false;
    error.value =
      e instanceof Error
        ? e.name === "NotAllowedError"
          ? "Разрешите доступ к микрофону в настройках браузера"
          : e.message
        : "Нет доступа к микрофону";
  }
}

function finishMicRecording(upload: boolean): void {
  const rec = micRecorder.value;
  if (!rec || rec.state === "inactive") {
    stopMicTracks();
    micRecorder.value = null;
    isRecording.value = false;
    recordChunks.value = [];
    return;
  }
  rec.onstop = () => {
    const chunks = [...recordChunks.value];
    recordChunks.value = [];
    const mime = rec.mimeType || "audio/webm";
    micRecorder.value = null;
    stopMicTracks();
    isRecording.value = false;
    if (!upload) return;
    const blob = new Blob(chunks, { type: mime });
    if (blob.size < 64) {
      error.value = "Запись слишком короткая";
      return;
    }
    const ext = mime.includes("webm") ? "webm" : mime.includes("mp4") ? "m4a" : "webm";
    void uploadVoiceBlob(blob, `voice-${Date.now()}.${ext}`);
  };
  rec.stop();
}

async function scheduleReminder(): Promise<void> {
  if (!reminderAt.value) return;
  error.value = "";
  reminderBusy.value = true;
  try {
    const iso = new Date(reminderAt.value).toISOString();
    await api(`/leads/${id.value}/reminders`, { method: "POST", json: { remind_at: iso } });
    reminderAt.value = "";
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось сохранить напоминание";
  } finally {
    reminderBusy.value = false;
  }
}

async function saveCallback(): Promise<void> {
  error.value = "";
  callbackBusy.value = true;
  try {
    await api(`/leads/${id.value}/callback`, {
      method: "PATCH",
      json: {
        callback_at: callbackAtLocal.value ? new Date(callbackAtLocal.value).toISOString() : null,
        callback_note: callbackNote.value.trim() || null,
      },
    });
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось сохранить";
  } finally {
    callbackBusy.value = false;
  }
}

async function clearCallback(): Promise<void> {
  if (!confirm("Сбросить дату перезвона и комментарий?")) return;
  error.value = "";
  callbackBusy.value = true;
  try {
    await api(`/leads/${id.value}/callback`, {
      method: "PATCH",
      json: { callback_at: null, callback_note: null },
    });
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
  } finally {
    callbackBusy.value = false;
  }
}

function formatStepValue(v: unknown): string {
  if (v == null) return "—";
  if (Array.isArray(v)) return v.map(String).join(", ");
  return String(v);
}

function answerRows(a: Record<string, unknown>): { key: string; k: string; v: string }[] {
  const rows: { key: string; k: string; v: string }[] = [];
  const steps = a.steps;
  if (Array.isArray(steps) && steps.length) {
    steps.forEach((raw, i) => {
      if (!raw || typeof raw !== "object") return;
      const o = raw as { title?: unknown; id?: unknown; value?: unknown };
      const title = String(o.title ?? o.id ?? "?");
      const id = o.id != null && String(o.id) !== "" ? String(o.id) : `step-${i}`;
      rows.push({ key: `${id}-${i}`, k: title, v: formatStepValue(o.value) });
    });
    return rows;
  }
  if (a.room_type) rows.push({ key: "room_type", k: "Тип помещения", v: String(a.room_type) });
  if (Array.isArray(a.zones)) rows.push({ key: "zones", k: "Зоны", v: (a.zones as string[]).join(", ") });
  if (a.area_sqm != null) rows.push({ key: "area", k: "Площадь", v: `${a.area_sqm} м²` });
  if (a.style) rows.push({ key: "style", k: "Стиль", v: String(a.style) });
  if (a.budget) rows.push({ key: "budget", k: "Бюджет", v: String(a.budget) });
  return rows;
}

const telHref = computed(() => (lead.value ? `tel:${lead.value.phone.replace(/\s/g, "")}` : "#"));
</script>

<template>
  <div class="space-y-5 sm:space-y-7">
    <RouterLink
      to="/manager"
      class="inline-flex items-center gap-1 text-sm font-bold text-accent-dim transition hover:gap-2 hover:text-accent"
    >
      ← К списку
    </RouterLink>
    <p v-if="error" class="text-red-600 dark:text-red-400">{{ error }}</p>
    <div v-else-if="!lead" class="text-ink-800/60 dark:text-ink-500">Загрузка…</div>
    <template v-else>
      <div
        v-if="isAdmin"
        class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
      >
        Вы вошли как администратор. Назначения и пул —
        <RouterLink to="/admin/leads" class="font-medium underline">Заявки в админке</RouterLink>
        .
      </div>

      <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between lg:gap-8">
        <div class="min-w-0 flex-1">
          <p class="text-xs font-bold uppercase tracking-wider text-accent-dim sm:text-sm">Заявка {{ lead.request_number }}</p>
          <h1 class="font-display mt-1 text-2xl font-bold tracking-tight text-ink-950 dark:text-ink-50 sm:text-3xl">
            {{ lead.name }}
          </h1>
          <p class="text-ink-800/80 dark:text-ink-300">{{ statusLabelRu(lead.status) }}</p>
          <p class="mt-1 text-xs text-ink-800/60 dark:text-ink-500">
            Создана: {{ formatDateTimeMsk(lead.created_at)
            }}<span v-if="lead.updated_at"> · обновлена: {{ formatDateTimeMsk(lead.updated_at) }}</span>
          </p>
          <p
            v-if="lead.utm_source || lead.page_url"
            class="mt-2 max-w-2xl break-words text-xs text-ink-700/90 dark:text-ink-400"
          >
            <span v-if="lead.utm_source"><span class="font-medium">utm_source:</span> {{ lead.utm_source }}</span>
            <span v-if="lead.utm_source && lead.page_url"> · </span>
            <span v-if="lead.page_url"><span class="font-medium">page_url:</span> {{ lead.page_url }}</span>
          </p>
        </div>
        <div class="flex flex-wrap gap-2 sm:gap-3">
          <a
            :href="telHref"
            class="inline-flex min-h-11 items-center justify-center rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-ink-950 shadow-md shadow-accent/25 transition hover:bg-accent-dim active:scale-[0.99]"
          >
            Позвонить
          </a>
          <button
            v-if="isPool && !isAdmin"
            type="button"
            class="inline-flex min-h-11 items-center justify-center rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-ink-950 shadow-md shadow-accent/25 transition hover:bg-accent-dim disabled:opacity-50 active:scale-[0.99]"
            :disabled="claimBusy"
            @click="claimLead"
          >
            {{ claimBusy ? "…" : "Взять в работу" }}
          </button>
          <button
            v-if="isMineActive"
            type="button"
            class="inline-flex min-h-11 items-center justify-center rounded-xl border border-ink-200/90 bg-white px-4 py-2.5 text-sm font-semibold shadow-sm transition hover:bg-ink-50 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100 dark:hover:bg-ink-800"
            @click="releaseLead"
          >
            Вернуть в пул
          </button>
          <button
            v-if="isMineActive"
            type="button"
            class="inline-flex min-h-11 items-center justify-center rounded-xl border border-ink-200/90 bg-white px-4 py-2.5 text-sm font-semibold shadow-sm transition hover:bg-ink-50 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100 dark:hover:bg-ink-800"
            @click="completeLead"
          >
            Завершить
          </button>
        </div>
      </div>

      <div class="surface-panel shadow-lift ring-1 ring-ink-200/40 dark:ring-ink-700/50">
        <h2 class="font-display text-lg font-bold text-ink-950 dark:text-ink-50">ИИ-резюме для звонка</h2>
        <p class="mt-2 leading-relaxed text-ink-900 dark:text-ink-100">{{ lead.ai_summary }}</p>
      </div>

      <div
        v-if="lead.ai_summary_client"
        class="surface-panel border-accent/20 bg-gradient-to-br from-ink-50/95 to-white ring-1 ring-accent/15 dark:border-accent/25 dark:from-ink-800/80 dark:to-ink-900/95 dark:ring-accent/10"
      >
        <h2 class="font-display text-lg font-bold text-ink-950 dark:text-ink-50">Как видит клиент</h2>
        <p class="mt-2 text-sm text-ink-700 dark:text-ink-300">Текст с экрана квиза и публичной страницы заявки</p>
        <p class="mt-2 leading-relaxed text-ink-900 dark:text-ink-100">{{ lead.ai_summary_client }}</p>
      </div>

      <div
        class="surface-panel border-amber-200/70 bg-gradient-to-br from-amber-50/80 to-white dark:border-amber-900/40 dark:from-amber-950/30 dark:to-ink-900/90"
      >
        <h2 class="font-display text-lg font-bold text-ink-950 dark:text-ink-50">Скрипт звонка</h2>
        <pre class="mt-2 whitespace-pre-wrap font-sans text-sm text-ink-900 dark:text-ink-100">{{ lead.call_script }}</pre>
      </div>

      <div class="surface-panel overflow-hidden">
        <h2 class="font-display text-lg font-bold text-ink-950 dark:text-ink-50">Ответы квиза</h2>
        <div class="-mx-1 mt-4 overflow-x-auto sm:mx-0">
          <table class="w-full min-w-[280px] text-sm">
            <tbody>
            <tr
              v-for="row in answerRows(lead.answers || {})"
              :key="row.key"
              class="border-t border-ink-100 first:border-t-0 dark:border-ink-700"
            >
              <td class="py-3 pr-4 align-top text-ink-800/70 dark:text-ink-400">{{ row.k }}</td>
              <td class="py-3 font-medium leading-snug dark:text-ink-100">{{ row.v }}</td>
            </tr>
          </tbody>
        </table>
        </div>
      </div>

      <div class="surface-panel">
        <h2 class="font-display text-lg font-bold text-ink-950 dark:text-ink-50">Заметки</h2>
        <ul class="mt-4 space-y-2 text-sm">
          <li
            v-for="n in lead.notes"
            :key="n.id"
            class="rounded-xl border border-ink-100/80 bg-ink-50/90 px-3 py-2.5 dark:border-ink-700/80 dark:bg-ink-800/50"
          >
            <span class="text-xs text-ink-800/60 dark:text-ink-500">{{ formatDateTimeMsk(n.created_at) }}</span>
            <p class="text-ink-900 dark:text-ink-100">{{ n.body }}</p>
          </li>
        </ul>
        <p v-if="!canMutateNotes" class="mt-2 text-sm text-ink-600 dark:text-ink-400">
          Заметки и напоминания доступны после того, как заявка закреплена за вами (возьмите её из общего пула).
        </p>
        <template v-else>
          <div class="mt-4 flex flex-col gap-2 sm:flex-row sm:items-stretch">
            <input
              v-model="noteText"
              type="text"
              placeholder="Текст заметки"
              class="min-h-11 flex-1 rounded-xl border border-ink-200 bg-white px-4 py-2.5 shadow-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/25 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50"
              @keyup.enter="addNote"
            />
            <button
              type="button"
              class="min-h-11 shrink-0 rounded-xl bg-ink-950 px-5 text-sm font-bold text-white shadow-md transition hover:bg-ink-900 active:scale-[0.99] dark:bg-accent dark:text-ink-950 dark:hover:bg-accent-dim"
              @click="addNote"
            >
              Добавить
            </button>
          </div>
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <button
              v-if="!isRecording"
              type="button"
              class="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100 disabled:opacity-50 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-100 dark:hover:bg-red-950/60"
              :disabled="voiceBusy"
              @click="startMicRecording"
            >
              <span class="inline-block h-2 w-2 rounded-full bg-red-600" aria-hidden="true" />
              Голосовой ввод
            </button>
            <template v-else>
              <button
                type="button"
                class="rounded-xl bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700"
                :disabled="voiceBusy"
                @click="finishMicRecording(true)"
              >
                Остановить и отправить
              </button>
              <button
                type="button"
                class="rounded-xl border border-ink-200 px-3 py-2 text-sm font-medium dark:border-ink-600"
                :disabled="voiceBusy"
                @click="finishMicRecording(false)"
              >
                Отменить
              </button>
              <span class="text-sm font-medium text-red-600 dark:text-red-400">Идёт запись…</span>
            </template>
            <span v-if="voiceBusy && !isRecording" class="text-xs text-ink-800/60">Отправка…</span>
          </div>
        </template>
      </div>

      <div v-if="canMutateNotes" class="surface-panel">
        <h2 class="font-display text-lg font-bold text-ink-950 dark:text-ink-50">Перезвонить позже</h2>
        <p class="mt-1 text-xs text-ink-800/70 dark:text-ink-500">
          Дата и заметка в карточке заявки (для вас и коллег). Отдельно от Telegram-напоминания ниже.
        </p>
        <p v-if="lead.callback_at" class="mt-3 text-sm text-ink-800 dark:text-ink-200">
          Сейчас:
          <span class="font-medium">{{ formatDateTimeMsk(lead.callback_at) }}</span>
          <span v-if="lead.callback_note" class="mt-1 block text-ink-700 dark:text-ink-300">{{ lead.callback_note }}</span>
        </p>
        <div class="mt-4 flex flex-col gap-3">
          <label class="block text-sm text-ink-800 dark:text-ink-300">
            Когда перезвонить
            <input
              v-model="callbackAtLocal"
              type="datetime-local"
              class="mt-2 min-h-11 w-full max-w-md rounded-xl border border-ink-200 bg-white px-3 py-2 shadow-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50"
            />
          </label>
          <label class="block text-sm text-ink-800 dark:text-ink-300">
            Комментарий
            <input
              v-model="callbackNote"
              type="text"
              maxlength="500"
              placeholder="Например: клиент на объекте после 15:00"
              class="mt-2 min-h-11 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 shadow-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50"
            />
          </label>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="min-h-11 rounded-xl bg-ink-900 px-5 text-sm font-bold text-white shadow-md transition hover:bg-ink-800 active:scale-[0.99] dark:bg-accent dark:text-ink-950 dark:hover:bg-accent-dim"
              :disabled="callbackBusy"
              @click="saveCallback"
            >
              {{ callbackBusy ? "…" : "Сохранить" }}
            </button>
            <button
              v-if="lead.callback_at || lead.callback_note"
              type="button"
              class="min-h-11 rounded-xl border border-ink-200 px-5 text-sm font-semibold transition hover:bg-ink-50 dark:border-ink-600 dark:hover:bg-ink-800"
              :disabled="callbackBusy"
              @click="clearCallback"
            >
              Сбросить
            </button>
          </div>
        </div>
      </div>

      <div v-if="canMutateNotes" class="surface-panel">
        <h2 class="font-display text-lg font-bold text-ink-950 dark:text-ink-50">Напоминание в Telegram</h2>
        <p class="mt-1 text-xs text-ink-800/70 dark:text-ink-500">
          Как «Перезвонить позже»: ниже видно все запланированные напоминания по этой заявке. Бот отправит их
          менеджеру в личку в указанное время.
        </p>
        <div v-if="sortedReminders.length" class="mt-4 space-y-2 rounded-xl border border-ink-200/90 bg-ink-50/80 p-4 dark:border-ink-700 dark:bg-ink-900/40">
          <p class="text-xs font-semibold uppercase tracking-wide text-ink-600 dark:text-ink-400">Запланировано</p>
          <ul class="space-y-2 text-sm text-ink-800 dark:text-ink-200">
            <li
              v-for="r in sortedReminders"
              :key="r.id"
              class="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink-200/60 pb-2 last:border-0 last:pb-0 dark:border-ink-700/60"
            >
              <span class="font-medium tabular-nums">{{ formatDateTimeMsk(r.remind_at) }}</span>
              <span
                class="text-xs font-semibold"
                :class="r.sent ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-800 dark:text-amber-300'"
              >
                {{ r.sent ? "Отправлено в Telegram" : "Ожидает отправки" }}
              </span>
              <span v-if="isAdmin && r.manager_name" class="w-full text-xs text-ink-600 dark:text-ink-400">
                Кому: {{ r.manager_name }}
              </span>
            </li>
          </ul>
        </div>
        <div class="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
          <input
            v-model="reminderAt"
            type="datetime-local"
            class="min-h-11 w-full min-w-0 flex-1 rounded-xl border border-ink-200 bg-white px-3 py-2 shadow-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50 sm:max-w-xs"
          />
          <button
            type="button"
            class="min-h-11 rounded-xl bg-ink-900 px-5 text-sm font-bold text-white shadow-md transition hover:bg-ink-800 active:scale-[0.99] disabled:opacity-50 dark:bg-accent dark:text-ink-950 dark:hover:bg-accent-dim"
            :disabled="reminderBusy"
            @click="scheduleReminder"
          >
            {{ reminderBusy ? "…" : "Добавить" }}
          </button>
        </div>
        <p v-if="isAdmin && lead?.assigned_manager_id" class="mt-2 text-xs text-ink-700 dark:text-ink-400">
          Админ: напоминание уйдёт в Telegram <span class="font-semibold">назначенному</span> менеджеру по этой заявке.
        </p>
        <p v-else-if="isAdmin && !lead?.assigned_manager_id" class="mt-2 text-xs text-amber-800 dark:text-amber-200">
          Заявка без назначения — напоминание придёт вам (админу) в Telegram.
        </p>
      </div>
    </template>
  </div>
</template>
