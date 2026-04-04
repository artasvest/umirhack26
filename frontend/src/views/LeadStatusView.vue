<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { api, statusLabelRu, type LeadPublic } from "@/api/client";

const route = useRoute();
const id = computed(() => route.params.id as string);
const data = ref<LeadPublic | null>(null);
const error = ref("");
let timer: ReturnType<typeof setInterval> | null = null;

async function load(): Promise<void> {
  try {
    data.value = await api<LeadPublic>(`/leads/${id.value}`);
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось загрузить";
  }
}

onMounted(() => {
  void load();
  timer = setInterval(() => void load(), 5000);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});

function formatStepValue(v: unknown): string {
  if (v == null) return "—";
  if (Array.isArray(v)) return v.map(String).join(", ");
  return String(v);
}

function formatAnswers(a: Record<string, unknown>): { key: string; label: string; value: string }[] {
  const rows: { key: string; label: string; value: string }[] = [];
  const steps = a.steps;
  if (Array.isArray(steps) && steps.length) {
    steps.forEach((raw, i) => {
      if (!raw || typeof raw !== "object") return;
      const o = raw as { title?: unknown; id?: unknown; value?: unknown };
      const title = String(o.title ?? o.id ?? "?");
      const id = o.id != null && String(o.id) !== "" ? String(o.id) : `step-${i}`;
      rows.push({ key: `${id}-${i}`, label: title, value: formatStepValue(o.value) });
    });
    return rows;
  }
  if (a.room_type) rows.push({ key: "room_type", label: "Тип помещения", value: String(a.room_type) });
  if (Array.isArray(a.zones)) rows.push({ key: "zones", label: "Зоны", value: (a.zones as string[]).join(", ") });
  if (a.area_sqm != null) rows.push({ key: "area", label: "Площадь", value: `${a.area_sqm} м²` });
  if (a.style) rows.push({ key: "style", label: "Стиль", value: String(a.style) });
  if (a.budget) rows.push({ key: "budget", label: "Бюджет", value: String(a.budget) });
  return rows;
}

const publicAnswerRows = computed(() => formatAnswers(data.value?.answers || {}));
</script>

<template>
  <div class="min-h-screen bg-gradient-to-b from-ink-50 to-white px-4 py-10">
    <div class="mx-auto max-w-lg">
      <RouterLink to="/" class="text-sm font-medium text-accent-dim hover:underline">← На главную</RouterLink>

      <div v-if="error" class="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-red-800">{{ error }}</div>

      <div v-else-if="!data" class="mt-10 text-center text-ink-800/70">Загрузка…</div>

      <div v-else class="mt-8 space-y-6">
        <div class="rounded-3xl border border-ink-200 bg-white p-8 shadow-lift">
          <p class="text-sm uppercase tracking-wider text-accent-dim">Заявка</p>
          <p class="mt-1 font-mono text-2xl font-bold text-ink-950">{{ data.request_number }}</p>
          <p class="mt-4 text-sm text-ink-800/70">Статус</p>
          <p class="mt-1 inline-flex rounded-full bg-ink-100 px-3 py-1 text-sm font-semibold text-ink-900">
            {{ statusLabelRu(data.status) }}
          </p>
          <p class="mt-2 text-xs text-ink-800/60">Обновляется автоматически каждые 5 секунд</p>
        </div>

        <div class="rounded-2xl border border-ink-200 bg-white p-6 shadow-card">
          <h2 class="font-display text-lg font-semibold text-ink-950">Ваши ответы</h2>
          <p v-if="publicAnswerRows.length === 0" class="mt-4 text-sm text-ink-800/70">Ответы не сохранены</p>
          <table v-else class="mt-4 w-full text-sm">
            <tbody>
              <tr v-for="row in publicAnswerRows" :key="row.key" class="border-t border-ink-100">
                <td class="py-2 pr-4 text-ink-800/70">{{ row.label }}</td>
                <td class="py-2 font-medium text-ink-900">{{ row.value }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
