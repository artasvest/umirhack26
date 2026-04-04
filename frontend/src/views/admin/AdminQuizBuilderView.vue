<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { api } from "@/api/client";
import type { QuizSchema } from "@/types/quiz-schema";
import QuizFlowEditor from "@/components/quiz-builder/QuizFlowEditor.vue";

interface QuizListRow {
  id: number;
  name: string;
  is_active: boolean;
}

interface QuizRowFull {
  id: number;
  name: string;
  schema: QuizSchema;
  is_active: boolean;
}

const route = useRoute();
const router = useRouter();

const flowRef = ref<InstanceType<typeof QuizFlowEditor> | null>(null);
const list = ref<QuizListRow[]>([]);
const selectedId = ref<number | null>(null);
const editName = ref("");
const schema = ref<QuizSchema | null>(null);
const jsonPreview = ref("");
const showJson = ref(false);
const error = ref("");
/** После «Сохранить»: предупреждения проверки схемы (черновик на сервере уже записан). */
const schemaValidationHint = ref("");
const saved = ref(false);
const loading = ref(false);
const listLoading = ref(true);
const activating = ref(false);
const jsonFileInput = ref<HTMLInputElement | null>(null);

const isSelectedActive = computed(() => {
  const id = selectedId.value;
  if (id == null) return false;
  return list.value.some((r) => r.id === id && r.is_active);
});

function parseQueryId(): number | null {
  const q = route.query.id;
  if (q === undefined || q === null || q === "") return null;
  const n = parseInt(String(q), 10);
  return Number.isFinite(n) ? n : null;
}

function pickDefaultId(rows: QuizListRow[]): number | null {
  if (!rows.length) return null;
  const active = rows.find((r) => r.is_active);
  return active?.id ?? rows[0]!.id;
}

async function loadList(opts?: { silent?: boolean }): Promise<void> {
  const silent = opts?.silent === true;
  if (!silent) listLoading.value = true;
  try {
    list.value = await api<QuizListRow[]>("/admin/quiz-schemas");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка списка квизов";
    list.value = [];
  } finally {
    if (!silent) listLoading.value = false;
  }
}

async function loadSelected(): Promise<void> {
  const id = selectedId.value;
  if (id == null) {
    schema.value = null;
    jsonPreview.value = "";
    return;
  }
  loading.value = true;
  try {
    const row = await api<QuizRowFull>(`/admin/quiz-schemas/${id}`);
    editName.value = row.name || "";
    schema.value = row.schema;
    jsonPreview.value = JSON.stringify(row.schema, null, 2);
    error.value = "";
    schemaValidationHint.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка загрузки";
    schema.value = null;
  } finally {
    loading.value = false;
  }
}

function syncSelectionFromRoute(rows: QuizListRow[]): void {
  const fromQ = parseQueryId();
  let id = fromQ != null && rows.some((r) => r.id === fromQ) ? fromQ : null;
  if (id == null) id = pickDefaultId(rows);
  selectedId.value = id;
  if (id != null && String(id) !== String(route.query.id ?? "")) {
    void router.replace({ name: "admin-quiz", query: { id: String(id) } });
  }
}

async function bootstrap(): Promise<void> {
  await loadList();
  syncSelectionFromRoute(list.value);
  await loadSelected();
}

function onSelectQuiz(idStr: string): void {
  const id = parseInt(idStr, 10);
  if (!Number.isFinite(id)) return;
  selectedId.value = id;
  void router.replace({ name: "admin-quiz", query: { id: String(id) } });
  void loadSelected();
}

onMounted(() => void bootstrap());

watch(
  () => route.query.id,
  async () => {
    if (listLoading.value) return;
    const fromQ = parseQueryId();
    if (fromQ == null) return;
    if (!list.value.some((r) => r.id === fromQ)) return;
    if (selectedId.value === fromQ) return;
    selectedId.value = fromQ;
    await loadSelected();
  },
);

/** Одна кнопка «Сохранить»: при открытом блоке JSON сначала пробуем поле, иначе схему с канваса. */
function resolveSchemaForSave(): QuizSchema | null {
  if (showJson.value) {
    try {
      const p = JSON.parse(jsonPreview.value) as QuizSchema;
      if (p?.nodes?.length) return p;
    } catch {
      /* дальше — канвас */
    }
  }
  const fromFlow = flowRef.value?.getSchema();
  if (fromFlow?.nodes?.length) return fromFlow;
  if (!showJson.value) {
    try {
      const p = JSON.parse(jsonPreview.value) as QuizSchema;
      if (p?.nodes?.length) return p;
    } catch {
      /* */
    }
  }
  return null;
}

async function saveQuiz(): Promise<void> {
  saved.value = false;
  schemaValidationHint.value = "";
  const id = selectedId.value;
  if (id == null) {
    error.value = "Выберите квиз в списке";
    return;
  }
  try {
    const s = resolveSchemaForSave();
    if (!s?.nodes?.length) {
      error.value = showJson.value
        ? "В поле JSON нет корректной схемы с блоками — проверьте синтаксис или сверните JSON и сохраните с канваса"
        : "Нет блоков для сохранения";
      return;
    }
    await api<QuizRowFull>(`/admin/quiz-schemas/${id}`, {
      method: "PUT",
      json: { name: editName.value.trim() || undefined, schema: s },
    });
    // Не подменяем schema — новая ссылка перезапускает watch в QuizFlowEditor и сбрасывает канвас.
    jsonPreview.value = JSON.stringify(s, null, 2);

    const v = await api<{ ok: boolean; errors: string[] }>("/admin/quiz-schemas/validate", {
      method: "POST",
      json: { name: editName.value.trim() || "default", schema: s },
    });
    error.value = "";
    saved.value = true;
    if (!v.ok) {
      schemaValidationHint.value = v.errors.length
        ? `Сохранено, но схема не готова к публикации: ${v.errors.join("; ")}`
        : "Сохранено, но схема не прошла проверку.";
    } else {
      schemaValidationHint.value = "";
    }

    await loadList({ silent: true });
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка сохранения";
  }
}

async function makeActive(): Promise<void> {
  const id = selectedId.value;
  if (id == null) return;
  activating.value = true;
  error.value = "";
  try {
    await api<QuizRowFull>(`/admin/quiz-schemas/${id}/activate`, { method: "POST" });
    await loadList({ silent: true });
    await loadSelected();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось активировать";
  } finally {
    activating.value = false;
  }
}

function triggerJsonFilePick(): void {
  jsonFileInput.value?.click();
}

function onJsonFileSelected(ev: Event): void {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const text = String(reader.result ?? "");
      const parsed = JSON.parse(text) as QuizSchema;
      jsonPreview.value = JSON.stringify(parsed, null, 2);
      schema.value = parsed;
      saved.value = false;
      error.value = "";
    } catch {
      error.value = "Файл не похож на корректный JSON схемы";
    }
  };
  reader.readAsText(file, "UTF-8");
}

function downloadJson(): void {
  let obj: QuizSchema;
  try {
    const fromFlow = flowRef.value?.getSchema();
    if (fromFlow && Array.isArray(fromFlow.nodes)) {
      obj = fromFlow;
    } else {
      obj = JSON.parse(jsonPreview.value) as QuizSchema;
    }
  } catch {
    error.value = "Не удалось собрать JSON для скачивания";
    return;
  }
  error.value = "";
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const raw = (editName.value.trim() || `quiz-${selectedId.value ?? "schema"}`).replace(/[<>:"/\\|?*]/g, "_");
  a.download = `${raw.slice(0, 80)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-white">Конструктор квиза</h1>
        <p class="mt-1 max-w-2xl text-sm text-ink-700 dark:text-ink-300">
          Редактирование схемы в хранилище. Проверка графа выполняется при «Сохранить» (черновик всё равно записывается);
          «Сделать активным» включает уже сохранённую версию на сайте. Список квизов —
          <RouterLink to="/admin/quizzes" class="text-accent underline-offset-2 hover:underline">хранилище</RouterLink>.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-xl border border-ink-200 px-4 py-2 text-sm font-medium text-ink-800 hover:bg-ink-100 dark:border-ink-600 dark:text-ink-200 dark:hover:bg-ink-800"
          :disabled="listLoading || loading"
          @click="bootstrap()"
        >
          Обновить с сервера
        </button>
        <button
          type="button"
          class="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-ink-950 hover:bg-accent-dim"
          :disabled="selectedId == null || loading"
          @click="saveQuiz"
        >
          Сохранить
        </button>
        <button
          type="button"
          class="rounded-xl border border-emerald-600 bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40 dark:border-emerald-500 dark:bg-emerald-700 dark:hover:bg-emerald-600"
          :disabled="selectedId == null || loading || activating || isSelectedActive"
          @click="makeActive"
        >
          {{ activating ? "…" : "Сделать активным" }}
        </button>
      </div>
    </div>

    <div class="flex flex-wrap items-end gap-4 rounded-2xl border border-ink-200 bg-ink-50 p-4 dark:border-ink-700 dark:bg-ink-900/40">
      <label class="flex min-w-[220px] flex-col gap-1 text-sm">
        <span class="font-medium text-ink-800 dark:text-ink-200">Квиз из хранилища</span>
        <select
          class="rounded-xl border border-ink-200 bg-white px-3 py-2 text-ink-900 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-100"
          :value="selectedId ?? ''"
          :disabled="listLoading || !list.length"
          @change="onSelectQuiz(($event.target as HTMLSelectElement).value)"
        >
          <option v-if="!list.length" value="">Нет квизов</option>
          <option v-for="r in list" :key="r.id" :value="r.id">
            {{ r.name || "Без названия" }} #{{ r.id }}{{ r.is_active ? " · активен" : "" }}
          </option>
        </select>
      </label>
      <label class="flex min-w-[200px] flex-1 flex-col gap-1 text-sm">
        <span class="font-medium text-ink-800 dark:text-ink-200">Название (для списка)</span>
        <input
          v-model="editName"
          type="text"
          maxlength="128"
          class="rounded-xl border border-ink-200 bg-white px-3 py-2 text-ink-900 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-100"
          placeholder="Например, Весна 2026"
        />
      </label>
    </div>

    <p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <p v-if="saved && !schemaValidationHint" class="text-sm text-emerald-700 dark:text-emerald-400">Сохранено</p>
    <p v-if="saved && schemaValidationHint" class="text-sm text-amber-800 dark:text-amber-200/90">{{ schemaValidationHint }}</p>
    <p v-if="listLoading || (loading && !schema)" class="text-sm text-ink-500">Загрузка…</p>

    <QuizFlowEditor v-if="!listLoading && schema" ref="flowRef" :schema="schema" />

    <div class="rounded-2xl border border-ink-200 bg-ink-50 dark:border-ink-700 dark:bg-ink-900/30">
      <button
        type="button"
        class="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-ink-800 hover:bg-ink-100 dark:text-ink-200 dark:hover:bg-ink-800/50"
        @click="showJson = !showJson"
      >
        JSON (редактор, файл с компьютера, скачать)
        <span class="text-ink-500">{{ showJson ? "▼" : "▶" }}</span>
      </button>
      <div v-show="showJson" class="border-t border-ink-200 p-4 dark:border-ink-700">
        <input
          ref="jsonFileInput"
          type="file"
          accept=".json,application/json"
          class="sr-only"
          @change="onJsonFileSelected"
        />
        <textarea
          v-model="jsonPreview"
          class="min-h-[200px] w-full rounded-xl border border-ink-200 bg-white p-3 font-mono text-xs text-ink-900 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-100"
          spellcheck="false"
        />
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-xl border border-ink-200 px-4 py-2 text-sm text-ink-800 hover:bg-ink-100 dark:border-ink-600 dark:text-ink-200 dark:hover:bg-ink-800"
            @click="triggerJsonFilePick"
          >
            Загрузить JSON с компьютера
          </button>
          <button
            type="button"
            class="rounded-xl border border-ink-200 px-4 py-2 text-sm text-ink-800 hover:bg-ink-100 dark:border-ink-600 dark:text-ink-200 dark:hover:bg-ink-800"
            @click="downloadJson"
          >
            Скачать JSON на компьютер
          </button>
        </div>
        <p class="mt-3 text-xs text-ink-500 dark:text-ink-500">
          Чтобы записать правки из поля JSON на сервер, нажмите «Сохранить» сверху (пока блок JSON открыт, сохраняется
          именно он).
        </p>
      </div>
    </div>
  </div>
</template>
