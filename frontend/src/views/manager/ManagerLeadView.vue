<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { api, statusLabelRu, type LeadManagerDetail } from "@/api/client";

const route = useRoute();
const id = computed(() => route.params.id as string);
const lead = ref<LeadManagerDetail | null>(null);
const error = ref("");
const noteText = ref("");
const reminderAt = ref("");
const voiceBusy = ref(false);

async function load(): Promise<void> {
  try {
    lead.value = await api<LeadManagerDetail>(`/leads/${id.value}`);
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
  }
}

onMounted(() => void load());

async function setStatus(s: "in_progress" | "completed"): Promise<void> {
  await api(`/leads/${id.value}/status`, { method: "PATCH", json: { status: s } });
  await load();
}

async function addNote(): Promise<void> {
  if (!noteText.value.trim()) return;
  await api(`/leads/${id.value}/notes`, { method: "POST", json: { text: noteText.value.trim() } });
  noteText.value = "";
  await load();
}

async function onVoice(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  voiceBusy.value = true;
  try {
    const fd = new FormData();
    fd.append("file", file);
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

async function scheduleReminder(): Promise<void> {
  if (!reminderAt.value) return;
  const iso = new Date(reminderAt.value).toISOString();
  await api(`/leads/${id.value}/reminders`, { method: "POST", json: { remind_at: iso } });
  reminderAt.value = "";
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
  <div class="space-y-6">
    <RouterLink to="/manager" class="text-sm font-medium text-accent-dim hover:underline">← К списку</RouterLink>
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <div v-else-if="!lead" class="text-ink-800/60">Загрузка…</div>
    <template v-else>
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-sm text-ink-800/70">Заявка {{ lead.request_number }}</p>
          <h1 class="font-display text-2xl font-semibold text-ink-950">{{ lead.name }}</h1>
          <p class="text-ink-800/80">{{ statusLabelRu(lead.status) }}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <a :href="telHref" class="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-ink-950 hover:bg-accent-dim">Позвонить</a>
          <button type="button" class="rounded-xl border border-ink-200 bg-white px-4 py-2 text-sm font-medium hover:bg-ink-50" @click="setStatus('in_progress')">
            Взять в работу
          </button>
          <button type="button" class="rounded-xl border border-ink-200 bg-white px-4 py-2 text-sm font-medium hover:bg-ink-50" @click="setStatus('completed')">
            Завершить
          </button>
        </div>
      </div>

      <div class="rounded-2xl border border-ink-200 bg-white p-6 shadow-card">
        <h2 class="font-display text-lg font-semibold text-ink-950">ИИ-резюме</h2>
        <p class="mt-2 leading-relaxed text-ink-900">{{ lead.ai_summary }}</p>
      </div>

      <div class="rounded-2xl border border-ink-200 bg-amber-50/50 p-6 shadow-card">
        <h2 class="font-display text-lg font-semibold text-ink-950">Скрипт звонка</h2>
        <pre class="mt-2 whitespace-pre-wrap font-sans text-sm text-ink-900">{{ lead.call_script }}</pre>
      </div>

      <div class="rounded-2xl border border-ink-200 bg-white p-6 shadow-card">
        <h2 class="font-display text-lg font-semibold text-ink-950">Ответы квиза</h2>
        <table class="mt-4 w-full text-sm">
          <tbody>
            <tr v-for="row in answerRows(lead.answers || {})" :key="row.key" class="border-t border-ink-100">
              <td class="py-2 pr-4 text-ink-800/70">{{ row.k }}</td>
              <td class="py-2 font-medium">{{ row.v }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="rounded-2xl border border-ink-200 bg-white p-6 shadow-card">
        <h2 class="font-display text-lg font-semibold text-ink-950">Заметки</h2>
        <ul class="mt-4 space-y-2 text-sm">
          <li v-for="n in lead.notes" :key="n.id" class="rounded-lg bg-ink-50 px-3 py-2">
            <span class="text-xs text-ink-800/60">{{ new Date(n.created_at).toLocaleString() }}</span>
            <p class="text-ink-900">{{ n.body }}</p>
          </li>
        </ul>
        <div class="mt-4 flex flex-col gap-2 sm:flex-row">
          <input v-model="noteText" type="text" placeholder="Текст заметки" class="flex-1 rounded-xl border border-ink-200 px-3 py-2" @keyup.enter="addNote" />
          <button type="button" class="rounded-xl bg-ink-950 px-4 py-2 text-sm font-semibold text-white" @click="addNote">Добавить</button>
        </div>
        <div class="mt-4 flex flex-wrap items-center gap-2">
          <label class="text-sm text-ink-800">
            Голосовая заметка
            <input type="file" accept="audio/*" class="ml-2 text-sm" :disabled="voiceBusy" @change="onVoice" />
          </label>
          <span v-if="voiceBusy" class="text-xs text-ink-800/60">Загрузка…</span>
        </div>
      </div>

      <div class="rounded-2xl border border-ink-200 bg-white p-6 shadow-card">
        <h2 class="font-display text-lg font-semibold text-ink-950">Напоминание перезвонить</h2>
        <div class="mt-4 flex flex-wrap items-end gap-2">
          <input v-model="reminderAt" type="datetime-local" class="rounded-xl border border-ink-200 px-3 py-2" />
          <button type="button" class="rounded-xl bg-ink-900 px-4 py-2 text-sm font-semibold text-white" @click="scheduleReminder">Сохранить</button>
        </div>
        <p class="mt-2 text-xs text-ink-800/60">Бот отправит напоминание в Telegram (когда будет настроен планировщик).</p>
      </div>
    </template>
  </div>
</template>
