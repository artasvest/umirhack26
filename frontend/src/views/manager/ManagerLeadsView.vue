<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { api, statusLabelRu, type LeadListItem } from "@/api/client";
import { formatDateTimeMsk } from "@/utils/cabinetTime";

const MANAGER_MAX_ACTIVE = 5;

type Bucket = "pool" | "active" | "completed";

const bucket = ref<Bucket>("pool");
const items = ref<LeadListItem[]>([]);
const activeCount = ref(0);
const error = ref("");

const titleForBucket = computed(() => {
  switch (bucket.value) {
    case "pool":
      return "Общий пул";
    case "active":
      return "Мои в работе";
    case "completed":
      return "Мои завершённые";
    default:
      return "";
  }
});

async function loadActiveCount(): Promise<void> {
  try {
    const rows = await api<LeadListItem[]>(`/leads?bucket=active`);
    activeCount.value = rows.length;
  } catch {
    activeCount.value = 0;
  }
}

async function load(): Promise<void> {
  error.value = "";
  try {
    items.value = await api<LeadListItem[]>(`/leads?bucket=${bucket.value}`);
    await loadActiveCount();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
    items.value = [];
  }
}

onMounted(() => void load());

watch(bucket, () => void load());

function poolSince(row: LeadListItem): string {
  const t = row.pool_entered_at || row.created_at;
  return t ? formatDateTimeMsk(t) : "—";
}
</script>

<template>
  <div class="space-y-6 sm:space-y-8">
    <div class="space-y-3">
      <h1 class="font-display text-2xl font-bold tracking-tight text-ink-950 dark:text-ink-50 sm:text-3xl">Заявки</h1>
      <p class="max-w-3xl text-sm leading-relaxed text-ink-600 dark:text-ink-400 sm:text-base">
        В общем пуле заявку видят все менеджеры; после «Взять в работу» она закрепляется за вами (до
        {{ MANAGER_MAX_ACTIVE }} активных). Остальным она недоступна, пока вы не вернёте её в пул или не завершите.
      </p>
    </div>

    <div class="-mx-1 flex gap-2 overflow-x-auto pb-2 [-ms-overflow-style:none] [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:overflow-visible [&::-webkit-scrollbar]:hidden">
      <button
        v-for="b in [
          { k: 'pool' as const, l: 'Общий пул' },
          { k: 'active' as const, l: 'В работе' },
          { k: 'completed' as const, l: 'Завершённые' },
        ]"
        :key="b.k"
        type="button"
        class="shrink-0 rounded-full px-4 py-2.5 text-sm font-bold transition sm:min-h-0"
        :class="
          bucket === b.k
            ? 'bg-accent text-ink-950 shadow-md shadow-accent/20 ring-1 ring-accent/40 dark:bg-accent dark:text-ink-950'
            : 'bg-ink-100/90 text-ink-700 ring-1 ring-transparent hover:bg-ink-200 dark:bg-ink-800/90 dark:text-ink-200 dark:hover:bg-ink-700'
        "
        @click="bucket = b.k"
      >
        {{ b.l }}
        <span v-if="b.k === 'active'" class="ml-1 text-xs font-semibold opacity-90"
          >({{ activeCount }}/{{ MANAGER_MAX_ACTIVE }})</span
        >
      </button>
    </div>

    <p class="text-sm font-bold text-ink-800 dark:text-ink-200">{{ titleForBucket }}</p>
    <p v-if="error" class="text-red-600 dark:text-red-400">{{ error }}</p>

    <div
      class="surface-panel overflow-hidden !p-0 shadow-lift ring-1 ring-ink-200/50 dark:ring-ink-700/40"
    >
      <div class="overflow-x-auto">
        <table class="min-w-[640px] w-full text-left text-sm sm:min-w-full">
          <thead
            class="border-b border-ink-200 bg-ink-50/95 text-xs font-bold uppercase tracking-wide text-ink-700 dark:border-ink-700 dark:bg-ink-800/90 dark:text-ink-400 sm:text-sm sm:normal-case sm:tracking-normal"
          >
            <tr>
              <th class="whitespace-nowrap px-4 py-3.5 font-semibold sm:font-medium">Имя</th>
              <th class="whitespace-nowrap px-4 py-3.5 font-semibold sm:font-medium">Телефон</th>
              <th class="whitespace-nowrap px-4 py-3.5 font-semibold sm:font-medium">Тип</th>
              <th class="whitespace-nowrap px-4 py-3.5 font-semibold sm:font-medium">Бюджет</th>
              <th v-if="bucket !== 'pool'" class="whitespace-nowrap px-4 py-3.5 font-semibold sm:font-medium">
                Статус
              </th>
              <th v-if="bucket === 'pool'" class="whitespace-nowrap px-4 py-3.5 font-semibold sm:font-medium">
                В пуле с
              </th>
              <th v-if="bucket === 'active'" class="whitespace-nowrap px-4 py-3.5 font-semibold sm:font-medium">
                Перезвон
              </th>
              <th class="whitespace-nowrap px-4 py-3.5 font-semibold sm:font-medium">Создана</th>
              <th class="px-4 py-3.5"></th>
            </tr>
          </thead>
        <tbody>
          <tr
            v-for="row in items"
            :key="row.id"
            class="border-b border-ink-100 hover:bg-ink-50/50 dark:border-ink-700 dark:hover:bg-ink-800/40"
          >
              <td class="px-4 py-3.5 font-semibold text-ink-900 dark:text-ink-100">{{ row.name }}</td>
              <td class="px-4 py-3.5 font-mono text-xs">{{ row.phone }}</td>
              <td class="px-4 py-3.5">{{ row.room_type || "—" }}</td>
              <td class="px-4 py-3.5">{{ row.budget || "—" }}</td>
              <td v-if="bucket !== 'pool'" class="px-4 py-3.5">{{ statusLabelRu(row.status) }}</td>
              <td v-if="bucket === 'pool'" class="px-4 py-3.5 text-ink-800/80 dark:text-ink-300">
                {{ poolSince(row) }}
              </td>
              <td v-if="bucket === 'active'" class="max-w-[140px] px-4 py-3.5 text-xs text-ink-800/80 dark:text-ink-300">
                <span v-if="row.callback_at">{{ formatDateTimeMsk(row.callback_at) }}</span>
                <span v-else class="text-ink-500">—</span>
              </td>
              <td class="px-4 py-3.5 text-ink-800/70 dark:text-ink-400">{{ formatDateTimeMsk(row.created_at) }}</td>
              <td class="px-4 py-3.5">
                <RouterLink
                  :to="`/manager/leads/${row.id}`"
                  class="inline-flex font-bold text-accent-dim underline-offset-2 transition hover:text-accent hover:underline"
                >
                  Открыть
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!items.length && !error" class="p-8 text-center font-medium text-ink-800/60 dark:text-ink-500">Пусто</p>
    </div>
  </div>
</template>
