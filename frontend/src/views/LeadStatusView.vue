<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { api, type LeadPublic } from "@/api/client";

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

/** Индекс «текущего» шага; для завершённой заявки 3 — все шаги отмечены выполненными. */
const statusStepIndex = computed(() => {
  const s = data.value?.status;
  if (s === "pending") return 0;
  if (s === "in_progress") return 1;
  if (s === "completed") return 3;
  return 0;
});

const steps = [
  { key: "accepted", title: "Принято", desc: "Заявка получена" },
  { key: "work", title: "В работе", desc: "Мы с вами свяжемся" },
  { key: "done", title: "Завершено", desc: "Заявка обработана" },
] as const;
</script>

<template>
  <div class="page-shell px-4 py-8 pb-28 sm:px-6 sm:py-12 sm:pb-32">
    <div class="relative z-10 mx-auto w-full max-w-lg sm:max-w-xl">
      <RouterLink
        to="/"
        class="inline-flex items-center gap-1 text-sm font-bold text-accent-dim transition hover:gap-2 hover:text-accent"
      >
        ← На главную
      </RouterLink>

      <div
        v-if="error"
        class="mt-6 rounded-2xl border border-red-200 bg-red-50/95 p-4 text-red-800 shadow-card backdrop-blur-sm dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200 sm:rounded-3xl sm:p-5"
      >
        {{ error }}
      </div>

      <div v-else-if="!data" class="mt-12 text-center font-medium text-ink-800/70 dark:text-ink-400">Загрузка…</div>

      <div v-else class="mt-8 space-y-5 sm:space-y-6">
        <div class="surface-panel !p-6 shadow-lift ring-1 ring-ink-200/40 dark:ring-ink-700/50 sm:!p-8">
          <p class="text-xs font-bold uppercase tracking-[0.2em] text-accent-dim sm:text-sm">Заявка</p>
          <p class="mt-2 font-mono text-2xl font-bold tracking-tight text-ink-950 dark:text-ink-50 sm:text-3xl">
            {{ data.request_number }}
          </p>
          <p class="mt-6 text-sm font-medium text-ink-800 dark:text-ink-200">Прогресс</p>
          <ol class="mt-4 flex w-full items-start gap-1 sm:gap-2">
            <li
              v-for="(st, i) in steps"
              :key="st.key"
              class="flex flex-1 flex-col items-center text-center"
            >
              <div class="flex w-full items-center">
                <span
                  v-if="i > 0"
                  class="h-0.5 flex-1 rounded-full"
                  :class="i <= statusStepIndex ? 'bg-accent' : 'bg-ink-200 dark:bg-ink-700'"
                />
                <span
                  class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold transition-colors"
                  :class="
                    i < statusStepIndex
                      ? 'bg-accent text-ink-950'
                      : i === statusStepIndex
                        ? 'bg-accent/90 ring-2 ring-accent ring-offset-2 ring-offset-white dark:ring-offset-ink-900'
                        : 'bg-ink-100 text-ink-500 dark:bg-ink-800 dark:text-ink-400'
                  "
                >
                  {{ i < statusStepIndex ? "✓" : i + 1 }}
                </span>
                <span
                  v-if="i < steps.length - 1"
                  class="h-0.5 flex-1 rounded-full"
                  :class="i < statusStepIndex ? 'bg-accent' : 'bg-ink-200 dark:bg-ink-700'"
                />
              </div>
              <p class="mt-2 text-xs font-semibold text-ink-900 dark:text-ink-100 sm:text-sm">{{ st.title }}</p>
              <p class="mt-0.5 hidden text-[11px] text-ink-600 dark:text-ink-400 sm:block">{{ st.desc }}</p>
            </li>
          </ol>
          <p class="mt-4 text-xs text-ink-800/60 dark:text-ink-500">Обновляется автоматически каждые 5 секунд</p>
        </div>

        <div
          v-if="data.ai_summary_client"
          class="surface-panel-accent border-accent/30 !bg-gradient-to-br from-amber-50/90 to-white dark:!from-ink-800/90 dark:!to-ink-900/95"
        >
          <h2 class="font-display text-lg font-bold text-ink-950 dark:text-ink-50">Кратко по вашей заявке</h2>
          <p class="mt-3 leading-relaxed text-ink-900 dark:text-ink-100">{{ data.ai_summary_client }}</p>
        </div>

        <div class="surface-panel overflow-hidden">
          <h2 class="font-display text-lg font-bold text-ink-950 dark:text-ink-50">Ваши ответы</h2>
          <p v-if="publicAnswerRows.length === 0" class="mt-4 text-sm text-ink-800/70 dark:text-ink-400">
            Ответы не сохранены
          </p>
          <div v-else class="-mx-1 mt-4 overflow-x-auto sm:mx-0">
            <table class="w-full min-w-[280px] text-sm">
              <tbody>
                <tr
                  v-for="row in publicAnswerRows"
                  :key="row.key"
                  class="border-t border-ink-100 first:border-t-0 dark:border-ink-700"
                >
                  <td class="py-3 pr-4 align-top text-ink-800/70 dark:text-ink-400">{{ row.label }}</td>
                  <td class="py-3 font-medium leading-snug text-ink-900 dark:text-ink-100">{{ row.value }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
