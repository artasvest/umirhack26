<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getToken } from "@/api/client";

interface FunnelRow {
  step_key: string;
  views: number;
  drops: number;
}

interface DayRow {
  date: string;
  count: number;
}

const funnel = ref<FunnelRow[]>([]);
const leadsByDay = ref<DayRow[]>([]);
const error = ref("");

async function load(): Promise<void> {
  try {
    const token = getToken();
    const res = await fetch("/api/analytics", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(await res.text());
    const data = (await res.json()) as { funnel: FunnelRow[]; leads_by_day: DayRow[] };
    funnel.value = data.funnel;
    leadsByDay.value = data.leads_by_day;
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
  }
}

async function downloadCsv(): Promise<void> {
  const token = getToken();
  const res = await fetch("/api/analytics/export/csv", {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "leads.csv";
  a.click();
  URL.revokeObjectURL(url);
}

onMounted(() => void load());
</script>

<template>
  <div class="space-y-8">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="font-display text-2xl font-semibold">Аналитика</h1>
      <button type="button" class="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-ink-950 hover:bg-accent-dim" @click="downloadCsv">
        Экспорт CSV
      </button>
    </div>
    <p v-if="error" class="text-red-400">{{ error }}</p>

    <div class="rounded-2xl border border-ink-800 bg-ink-900/50 p-6">
      <h2 class="font-display text-lg font-semibold text-white">Воронка (просмотры / броски по шагам)</h2>
      <p class="mt-1 text-xs text-ink-400">События шлёт фронт квиза: step_view и step_drop</p>
      <div class="mt-4 overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="text-ink-400">
            <tr>
              <th class="px-2 py-2 text-left">Шаг</th>
              <th class="px-2 py-2 text-left">Просмотры</th>
              <th class="px-2 py-2 text-left">Броски</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in funnel" :key="row.step_key" class="border-t border-ink-800">
              <td class="px-2 py-2 font-mono text-xs">{{ row.step_key }}</td>
              <td class="px-2 py-2">{{ row.views }}</td>
              <td class="px-2 py-2">{{ row.drops }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!funnel.length" class="mt-4 text-ink-500">Пока нет событий</p>
      </div>
    </div>

    <div class="rounded-2xl border border-ink-800 bg-ink-900/50 p-6">
      <h2 class="font-display text-lg font-semibold text-white">Заявки по дням</h2>
      <ul class="mt-4 space-y-1 text-sm text-ink-200">
        <li v-for="d in leadsByDay" :key="d.date">{{ d.date }} — {{ d.count }}</li>
      </ul>
      <p v-if="!leadsByDay.length" class="mt-4 text-ink-500">Нет заявок</p>
    </div>
  </div>
</template>
