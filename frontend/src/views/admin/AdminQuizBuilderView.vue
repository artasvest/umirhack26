<script setup lang="ts">
import { ref } from "vue";
import { api } from "@/api/client";
import type { QuizSchema } from "@/types/quiz-schema";
import QuizFlowEditor from "@/components/quiz-builder/QuizFlowEditor.vue";

const flowRef = ref<InstanceType<typeof QuizFlowEditor> | null>(null);
const schema = ref<QuizSchema | null>(null);
const jsonPreview = ref("");
const showJson = ref(false);
const error = ref("");
const saved = ref(false);
const loading = ref(false);

async function load(): Promise<void> {
  loading.value = true;
  try {
    const row = await api<{ schema: QuizSchema }>("/quiz-schema");
    schema.value = row.schema as QuizSchema;
    jsonPreview.value = JSON.stringify(row.schema, null, 2);
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка загрузки";
  } finally {
    loading.value = false;
  }
}

void load();

async function saveFromFlow(): Promise<void> {
  saved.value = false;
  try {
    const s = flowRef.value?.getSchema();
    if (!s?.nodes?.length) {
      error.value = "Нет блоков для сохранения";
      return;
    }
    await api("/quiz-schema", { method: "POST", json: { name: "default", schema: s } });
    schema.value = s;
    jsonPreview.value = JSON.stringify(s, null, 2);
    saved.value = true;
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка сохранения";
  }
}

async function saveFromJson(): Promise<void> {
  saved.value = false;
  try {
    const parsed = JSON.parse(jsonPreview.value) as QuizSchema;
    await api("/quiz-schema", { method: "POST", json: { name: "default", schema: parsed } });
    schema.value = parsed;
    saved.value = true;
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Некорректный JSON";
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="font-display text-2xl font-semibold text-white">Конструктор квиза</h1>
        <p class="mt-1 max-w-2xl text-sm text-ink-300">
          Canvas на <span class="text-accent">Vue Flow</span>: перетаскивание блоков, связи между шагами, ветвление для одиночного выбора (ручка у каждого варианта). Схема сохраняется в
          <code class="text-accent">quiz_schema</code> и отдаётся через API.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-xl border border-ink-600 px-4 py-2 text-sm font-medium text-ink-200 hover:bg-ink-800"
          :disabled="loading"
          @click="load"
        >
          Обновить с сервера
        </button>
        <button
          type="button"
          class="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-ink-950 hover:bg-accent-dim"
          @click="saveFromFlow"
        >
          Сохранить схему
        </button>
      </div>
    </div>

    <p v-if="error" class="text-sm text-red-400">{{ error }}</p>
    <p v-if="saved" class="text-sm text-emerald-400">Сохранено</p>
    <p v-if="loading" class="text-sm text-ink-500">Загрузка…</p>

    <QuizFlowEditor v-if="!loading" ref="flowRef" :schema="schema" />

    <div class="rounded-2xl border border-ink-700 bg-ink-900/30">
      <button
        type="button"
        class="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-ink-200 hover:bg-ink-800/50"
        @click="showJson = !showJson"
      >
        JSON (редактор / импорт)
        <span class="text-ink-500">{{ showJson ? "▼" : "▶" }}</span>
      </button>
      <div v-show="showJson" class="border-t border-ink-700 p-4">
        <textarea
          v-model="jsonPreview"
          class="min-h-[200px] w-full rounded-xl border border-ink-600 bg-ink-950 p-3 font-mono text-xs text-ink-100"
          spellcheck="false"
        />
        <button type="button" class="mt-2 rounded-xl border border-ink-600 px-4 py-2 text-sm text-ink-200 hover:bg-ink-800" @click="saveFromJson">
          Сохранить из JSON
        </button>
      </div>
    </div>
  </div>
</template>
