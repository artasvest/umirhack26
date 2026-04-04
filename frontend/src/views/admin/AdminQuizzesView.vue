<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { api } from "@/api/client";
import type { QuizSchema } from "@/types/quiz-schema";

interface QuizListRow {
  id: number;
  name: string;
  is_active: boolean;
  updated_at?: string | null;
}

const router = useRouter();
const rows = ref<QuizListRow[]>([]);
const loading = ref(true);
const error = ref("");
const busyId = ref<number | null>(null);
const creating = ref(false);

interface QuizRowFull {
  id: number;
  name: string;
  schema: QuizSchema;
  is_active: boolean;
}

const sorted = computed(() => [...rows.value].sort((a, b) => b.id - a.id));

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    rows.value = await api<QuizListRow[]>("/admin/quiz-schemas");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось загрузить";
    rows.value = [];
  } finally {
    loading.value = false;
  }
}

async function activate(id: number): Promise<void> {
  busyId.value = id;
  error.value = "";
  try {
    await api(`/admin/quiz-schemas/${id}/activate`, { method: "POST" });
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось активировать";
  } finally {
    busyId.value = null;
  }
}

async function createNewQuiz(): Promise<void> {
  creating.value = true;
  error.value = "";
  try {
    const row = await api<QuizRowFull>("/admin/quiz-schemas", {
      method: "POST",
      json: {
        name: `Новый квиз ${new Date().toLocaleString("ru", { dateStyle: "short", timeStyle: "short" })}`,
        schema: { version: 1, nodes: [], edges: [] } satisfies QuizSchema,
      },
    });
    await load();
    await router.push({ name: "admin-quiz", query: { id: String(row.id) } });
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось создать квиз";
  } finally {
    creating.value = false;
  }
}

async function removeRow(id: number): Promise<void> {
  if (!confirm("Удалить этот квиз из хранилища? Аналитика и заявки с этим id останутся в БД, но строка схемы исчезнет.")) {
    return;
  }
  busyId.value = id;
  error.value = "";
  try {
    await api(`/admin/quiz-schemas/${id}`, { method: "DELETE" });
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось удалить";
  } finally {
    busyId.value = null;
  }
}

onMounted(() => void load());
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-ink-50">Хранилище квизов</h1>
        <p class="mt-1 max-w-2xl text-sm text-ink-600 dark:text-ink-400">
          Несколько схем в базе: на сайте показывается только активная. «Новый квиз» — пустая схема; копию другого можно собрать через JSON в конструкторе.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-ink-950 shadow-card transition hover:bg-accent-dim disabled:opacity-50 dark:bg-white dark:hover:bg-ink-200"
          :disabled="loading || creating"
          @click="createNewQuiz()"
        >
          {{ creating ? "Создание…" : "Создать новый квиз" }}
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-xl border border-ink-200 bg-white px-4 py-2 text-sm font-semibold text-ink-800 shadow-card transition hover:bg-ink-50 disabled:opacity-50 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100 dark:hover:bg-ink-800"
          :disabled="loading"
          @click="load()"
        >
          Обновить
        </button>
      </div>
    </div>

    <p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>

    <div
      v-if="loading && !rows.length"
      class="rounded-2xl border border-ink-200 bg-white p-10 text-center text-ink-500 shadow-card dark:border-ink-800 dark:bg-ink-900/60"
    >
      Загрузка…
    </div>

    <ul v-else class="space-y-3">
      <li
        v-for="r in sorted"
        :key="r.id"
        class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-ink-200 bg-white p-4 shadow-card dark:border-ink-800 dark:bg-ink-900/70"
      >
        <div>
          <p class="font-medium text-ink-900 dark:text-ink-100">
            {{ r.name || "Без названия" }}
            <span class="ml-2 text-xs font-normal text-ink-500">#{{ r.id }}</span>
          </p>
          <p v-if="r.is_active" class="mt-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
            Активен на сайте
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <RouterLink
            :to="{ name: 'admin-quiz', query: { id: String(r.id) } }"
            class="rounded-xl border border-ink-200 px-3 py-1.5 text-sm font-medium text-ink-800 hover:bg-ink-50 dark:border-ink-600 dark:text-ink-200 dark:hover:bg-ink-800"
          >
            Конструктор
          </RouterLink>
          <button
            v-if="!r.is_active"
            type="button"
            class="rounded-xl bg-accent px-3 py-1.5 text-sm font-semibold text-ink-950 hover:bg-accent-dim disabled:opacity-50 dark:bg-white dark:hover:bg-ink-200"
            :disabled="busyId === r.id"
            @click="activate(r.id)"
          >
            Сделать активным
          </button>
          <button
            v-if="!r.is_active"
            type="button"
            class="rounded-xl border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/40"
            :disabled="busyId === r.id"
            @click="removeRow(r.id)"
          >
            Удалить
          </button>
        </div>
      </li>
    </ul>

    <p v-if="!loading && !sorted.length" class="text-sm text-ink-500">Список пуст</p>
  </div>
</template>
