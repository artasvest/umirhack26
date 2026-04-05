<script setup lang="ts">
import { computed, ref } from "vue";
import { api, getToken } from "@/api/client";

interface FunnelRow {
  node_id: string;
  title: string;
  views: number;
  drops: number;
  drop_rate: number;
  /** Среднее время на шаге до следующего просмотра в сессии, сек */
  avg_seconds_on_step?: number | null;
}

interface DistOpt {
  label: string;
  count: number;
  percent: number;
}

interface DistBlock {
  node_id: string;
  title: string;
  options: DistOpt[];
}

interface Dashboard {
  total_started: number;
  total_completed: number;
  total_submitted: number;
  completion_rate: number;
  avg_time_seconds: number;
  funnel: FunnelRow[];
  top_drop_step: { node_id: string; title: string } | null;
  answer_distribution: DistBlock[];
  drop_idle_minutes?: number;
  /** null = весь трафик; иначе id квиза */
  quiz_filter_applied?: number | null;
  active_quiz_schema_id?: number | null;
}

interface QuizListRow {
  id: number;
  name: string;
  is_active: boolean;
}

interface ByQuizRow {
  quiz_schema_id: number;
  name: string;
  is_active: boolean;
  total_started: number;
  total_completed: number;
  total_submitted: number;
  completion_rate: number;
}

const data = ref<Dashboard | null>(null);
/** "" = активный квиз; "0" = весь трафик; иначе id строкой */
const filterQuiz = ref("");
const quizList = ref<QuizListRow[]>([]);
const byQuiz = ref<ByQuizRow[]>([]);
const loading = ref(true);
const error = ref("");

const maxFunnelViews = computed(() => {
  const f = data.value?.funnel ?? [];
  const m = Math.max(0, ...f.map((r) => r.views));
  return m || 1;
});

function fmtDuration(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m} мин ${r} сек`;
}

function dropBadgeClass(rate: number): string {
  if (rate > 30)
    return "bg-red-100 text-red-800 ring-1 ring-red-200 dark:bg-red-950/60 dark:text-red-300 dark:ring-red-500/30";
  if (rate >= 10)
    return "bg-amber-100 text-amber-900 ring-1 ring-amber-200 dark:bg-amber-950/50 dark:text-amber-200 dark:ring-amber-500/25";
  return "bg-emerald-100 text-emerald-900 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-500/20";
}

function analyticsQuerySuffix(): string {
  if (filterQuiz.value === "0") return "?quiz_schema_id=0";
  if (filterQuiz.value !== "") return `?quiz_schema_id=${encodeURIComponent(filterQuiz.value)}`;
  return "";
}

async function loadQuizList(): Promise<void> {
  try {
    quizList.value = await api<QuizListRow[]>("/admin/quiz-schemas");
  } catch {
    quizList.value = [];
  }
}

async function loadByQuiz(): Promise<void> {
  try {
    byQuiz.value = await api<ByQuizRow[]>("/admin/analytics/by-quiz");
  } catch {
    byQuiz.value = [];
  }
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const q = analyticsQuerySuffix();
    const [dash] = await Promise.all([
      api<Dashboard>(`/admin/analytics${q}`),
      loadQuizList(),
      loadByQuiz(),
    ]);
    data.value = dash;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось загрузить";
    data.value = null;
  } finally {
    loading.value = false;
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

void load();
</script>

<template>
  <div class="space-y-8">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-ink-50">Аналитика</h1>
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-xl border border-ink-200 bg-white px-4 py-2 text-sm font-semibold text-ink-800 shadow-card transition hover:border-ink-300 hover:bg-ink-50 disabled:opacity-50 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100 dark:hover:border-white/25 dark:hover:bg-ink-800"
          :disabled="loading"
          @click="load()"
        >
          <span
            v-if="loading"
            class="inline-block size-4 animate-spin rounded-full border-2 border-ink-300 border-t-ink-950 dark:border-ink-600 dark:border-t-accent"
            aria-hidden="true"
          />
          Обновить
        </button>
        <button
          type="button"
          class="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-ink-950 transition hover:bg-accent-dim dark:bg-white dark:hover:bg-ink-200"
          @click="downloadCsv"
        >
          Экспорт CSV
        </button>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-3 rounded-2xl border border-ink-200 bg-ink-50 px-4 py-3 dark:border-ink-700 dark:bg-ink-900/40">
      <label class="flex flex-wrap items-center gap-2 text-sm text-ink-800 dark:text-ink-200">
        <span class="font-medium">Данные дашборда:</span>
        <select
          v-model="filterQuiz"
          class="rounded-xl border border-ink-200 bg-white px-3 py-2 text-ink-900 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-100"
          :disabled="loading"
          @change="load()"
        >
          <option value="">Активный квиз (как на сайте)</option>
          <option value="0">Весь трафик (все квизы)</option>
          <option v-for="r in quizList" :key="r.id" :value="String(r.id)">
            {{ r.name || "Без названия" }} #{{ r.id }}{{ r.is_active ? " · активен" : "" }}
          </option>
        </select>
      </label>
      <p v-if="data" class="text-xs text-ink-500 dark:text-ink-500">
        <template v-if="data.quiz_filter_applied == null"> Показаны все события и заявки; воронка и подписи шагов — по активной схеме. </template>
        <template v-else> Фильтр: квиз #{{ data.quiz_filter_applied }}. </template>
      </p>
    </div>

    <section
      v-if="byQuiz.length"
      class="rounded-2xl border border-ink-200 bg-white p-5 shadow-card dark:border-ink-800 dark:bg-ink-900/70"
    >
      <h2 class="font-display text-lg font-semibold text-ink-950 dark:text-ink-50">Сравнение квизов</h2>
      <p class="mt-1 text-xs text-ink-500 dark:text-ink-400">
        Открытия и заявки привязаны к id схемы. Удобно сравнить конверсию между версиями.
      </p>
      <div class="mt-4 overflow-x-auto">
        <table class="w-full min-w-[520px] border-collapse text-left text-sm">
          <thead>
            <tr class="border-b border-ink-200 text-ink-500 dark:border-ink-700 dark:text-ink-400">
              <th class="py-2 pr-3 font-medium">Квиз</th>
              <th class="py-2 pr-3 font-medium">Открыли</th>
              <th class="py-2 pr-3 font-medium">До формы</th>
              <th class="py-2 pr-3 font-medium">Заявки</th>
              <th class="py-2 font-medium">Конверсия</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in byQuiz"
              :key="row.quiz_schema_id"
              class="border-b border-ink-100 dark:border-ink-800/80"
            >
              <td class="py-2 pr-3 text-ink-900 dark:text-ink-100">
                {{ row.name || "—" }}
                <span class="text-ink-400">#{{ row.quiz_schema_id }}</span>
                <span v-if="row.is_active" class="ml-1 text-xs text-emerald-600 dark:text-emerald-400">активен</span>
              </td>
              <td class="py-2 pr-3">{{ row.total_started }}</td>
              <td class="py-2 pr-3">{{ row.total_completed }}</td>
              <td class="py-2 pr-3">{{ row.total_submitted }}</td>
              <td class="py-2 font-medium text-accent dark:text-white">{{ row.completion_rate }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div
      v-if="loading && !data"
      class="rounded-2xl border border-ink-200 bg-white p-10 text-center text-ink-500 shadow-card dark:border-ink-800 dark:bg-ink-900/60 dark:text-ink-400"
    >
      Загрузка…
    </div>
    <div
      v-else-if="error"
      class="rounded-2xl border border-red-200 bg-red-50 p-10 text-center text-red-800 shadow-card dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-200"
    >
      {{ error }}
    </div>

    <template v-else-if="data">
      <div class="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div
          class="rounded-2xl border border-ink-200 bg-white p-5 shadow-card dark:border-ink-800 dark:bg-ink-900/70"
        >
          <p class="text-xs font-medium text-ink-500 dark:text-ink-400">Открыли квиз</p>
          <p class="mt-2 font-display text-2xl font-semibold text-ink-950 dark:text-ink-50">{{ data.total_started }}</p>
        </div>
        <div
          class="rounded-2xl border border-ink-200 bg-white p-5 shadow-card dark:border-ink-800 dark:bg-ink-900/70"
        >
          <p class="text-xs font-medium text-ink-500 dark:text-ink-400">Отправили заявку</p>
          <p class="mt-2 font-display text-2xl font-semibold text-ink-950 dark:text-ink-50">{{ data.total_submitted }}</p>
        </div>
        <div
          class="rounded-2xl border border-ink-200 bg-white p-5 shadow-card dark:border-ink-800 dark:bg-ink-900/70"
        >
          <p class="text-xs font-medium text-ink-500 dark:text-ink-400">Конверсия</p>
          <p class="mt-2 font-display text-2xl font-semibold text-accent dark:text-white">{{ data.completion_rate }}%</p>
        </div>
        <div
          class="rounded-2xl border border-ink-200 bg-white p-5 shadow-card dark:border-ink-800 dark:bg-ink-900/70"
        >
          <p class="text-xs font-medium text-ink-500 dark:text-ink-400">Среднее время</p>
          <p class="mt-2 font-display text-xl font-semibold text-ink-950 dark:text-ink-50">
            {{ fmtDuration(data.avg_time_seconds) }}
          </p>
        </div>
      </div>

      <p class="text-xs text-ink-600 dark:text-ink-500">
        Дошли до формы (сессий):
        <span class="font-medium text-ink-900 dark:text-ink-300">{{ data.total_completed }}</span>
      </p>

      <section
        class="rounded-2xl border border-ink-200 bg-white p-6 shadow-lift dark:border-ink-800 dark:bg-ink-900/50"
      >
        <h2 class="font-display text-lg font-semibold text-ink-950 dark:text-ink-50">Воронка по шагам</h2>
        <p class="mt-1 text-xs text-ink-500 dark:text-ink-500">
          Просмотры (step_view) · дропы: сессия без заявки и без активности
          <span class="font-medium text-ink-700 dark:text-ink-400"
            >{{ data.drop_idle_minutes ?? 30 }} мин</span
          >
          на последнем шаге · среднее время на блоке — до следующего шага в той же сессии (паузы длиннее порога
          обрезаются)
        </p>
        <ul class="mt-6 space-y-4">
          <li
            v-for="row in data.funnel"
            :key="row.node_id"
            class="rounded-xl border border-ink-200 bg-ink-50 px-3 py-3 transition dark:border-ink-800/80 dark:bg-ink-950/40"
            :class="
              data.top_drop_step?.node_id === row.node_id
                ? 'border-l-4 border-l-red-400 bg-red-50/80 pl-2 ring-1 ring-red-200 dark:border-l-red-400 dark:bg-red-950/35 dark:ring-red-500/20'
                : ''
            "
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span class="font-medium text-ink-900 dark:text-ink-100">{{ row.title }}</span>
              <div class="flex flex-wrap items-center gap-3 text-sm">
                <span
                  v-if="row.avg_seconds_on_step != null"
                  class="text-ink-600 dark:text-ink-400"
                  title="Среднее время на этом шаге до следующего step_view в сессии"
                >
                  ~{{ fmtDuration(row.avg_seconds_on_step) }}
                </span>
                <span v-else class="text-ink-400 dark:text-ink-600" title="Нет переходов на другой шаг в данных"
                  >—</span
                >
                <span class="text-ink-500">{{ row.views }} просм.</span>
              </div>
            </div>
            <div class="mt-2 flex items-center gap-3">
              <div class="h-2 flex-1 overflow-hidden rounded-full bg-ink-200 dark:bg-ink-800">
                <div
                  class="h-full rounded-full bg-accent transition-all dark:bg-white"
                  :style="{ width: `${maxFunnelViews ? (row.views / maxFunnelViews) * 100 : 0}%` }"
                />
              </div>
              <span
                class="shrink-0 rounded-lg px-2 py-0.5 text-xs font-medium"
                :class="dropBadgeClass(row.drop_rate)"
              >
                −{{ row.drops }} ({{ row.drop_rate }}%)
              </span>
            </div>
          </li>
        </ul>
        <p v-if="!data.funnel.length" class="mt-4 text-center text-sm text-ink-500">Нет данных воронки</p>
      </section>

      <section>
        <h2 class="mb-4 font-display text-lg font-semibold text-ink-950 dark:text-ink-50">Распределение ответов</h2>
        <p class="mb-4 text-xs text-ink-600 dark:text-ink-500">
          Считаются выборы по событиям квиза (в т.ч. без заявки); для отправленных заявок дубли с тем же
          session_id не суммируются.
        </p>
        <div class="space-y-4">
          <div
            v-for="block in data.answer_distribution"
            :key="block.node_id"
            class="rounded-2xl border border-ink-200 bg-white p-5 shadow-card dark:border-ink-800 dark:bg-ink-900/70"
          >
            <h3 class="font-medium text-ink-900 dark:text-ink-100">{{ block.title }}</h3>
            <ul class="mt-4 space-y-3">
              <li v-for="opt in block.options" :key="block.node_id + opt.label" class="space-y-1">
                <div class="flex justify-between gap-2 text-sm">
                  <span class="text-ink-800 dark:text-ink-200">{{ opt.label }}</span>
                  <span class="shrink-0 text-ink-500">{{ opt.count }} · {{ opt.percent }}%</span>
                </div>
                <div class="h-2 overflow-hidden rounded-full bg-ink-200 dark:bg-ink-800">
                  <div
                    class="h-full rounded-full bg-accent dark:bg-white"
                    :style="{ width: `${Math.min(100, opt.percent)}%` }"
                  />
                </div>
              </li>
            </ul>
          </div>
        </div>
        <p v-if="!data.answer_distribution.length" class="text-center text-sm text-ink-500">
          Пока нет данных по ответам (события step_answer или заявки)
        </p>
      </section>
    </template>
  </div>
</template>
