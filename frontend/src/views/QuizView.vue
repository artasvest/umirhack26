<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import QRCode from "qrcode";
import { api } from "@/api/client";
import type { QuizNode, QuizOption, QuizSchema } from "@/types/quiz-schema";
import { useSessionId } from "@/composables/useSessionId";
import {
  clearPersisted,
  loadPersisted,
  watchPersistSchema,
  type QuizFormState,
  type QuizStepEntry,
} from "@/composables/useQuizPersistence";
import { trackEvent } from "@/composables/trackAnalytics";

interface QuizSchemaApiRow {
  id: number;
  name: string;
  schema: QuizSchema;
  is_active: boolean;
}

function asSchema(raw: unknown): QuizSchema | null {
  if (!raw || typeof raw !== "object") return null;
  const s = raw as QuizSchema;
  if (!Array.isArray(s.nodes)) return null;
  return s;
}

function fingerprint(schema: QuizSchema): string {
  try {
    const sig = {
      v: schema.version ?? 0,
      n: (schema.nodes ?? []).map((x) => ({ i: x.id, t: x.type })),
      e: schema.edges ?? [],
    };
    return JSON.stringify(sig);
  } catch {
    return "";
  }
}

function findStartNodeId(schema: QuizSchema): string | null {
  const nodes = schema.nodes ?? [];
  if (!nodes.length) return null;
  const incoming = new Set((schema.edges ?? []).map((e) => e.to));
  const roots = nodes.filter((n) => !incoming.has(n.id));
  if (roots.length === 1) return roots[0].id;
  if (roots.length > 1)
    return [...roots].sort((a, b) => a.id.localeCompare(b.id))[0]?.id ?? null;
  return nodes[0].id;
}

function nodeById(schema: QuizSchema, id: string): QuizNode | undefined {
  return (schema.nodes ?? []).find((n) => n.id === id);
}

function resolveNext(schema: QuizSchema, node: QuizNode, opt?: QuizOption): string | null {
  if (opt?.nextStep) return opt.nextStep;
  if (node.nextStep) return node.nextStep;
  const edge = (schema.edges ?? []).find((e) => e.from === node.id);
  return edge?.to ?? null;
}

const sessionId = useSessionId();
const persistedSnap = loadPersisted();

const schemaRaw = ref<QuizSchema | null>(null);
const schemaLoading = ref(true);
const schemaError = ref("");
const flowError = ref("");
const successDone = ref(false);

const navStack = ref<string[]>([]);
const stepsCompleted = ref<QuizStepEntry[]>([]);
const answersByNode = ref<Record<string, unknown>>({});

const defaultForm = (): QuizFormState => ({
  name: "",
  phoneDigits: "",
  email: "",
  comment: "",
  consent: false,
});

const form = ref<QuizFormState>(defaultForm());
const aiSummary = ref("");
const summaryLoading = ref(false);
const imgError = ref<Record<string, boolean>>({});

const schemaFp = ref("");

const schema = computed(() => schemaRaw.value);

watchPersistSchema(schemaFp, navStack, stepsCompleted, answersByNode, form, aiSummary);

const currentNodeId = computed(() => navStack.value[navStack.value.length - 1] ?? null);

const currentNode = computed((): QuizNode | null => {
  const s = schema.value;
  const id = currentNodeId.value;
  if (!s || !id) return null;
  return nodeById(s, id) ?? null;
});

/** step5 → 5; для ветвления без увеличения глубины стека */
function parseStepOrdinalFromId(nodeId: string): number | null {
  const m = /^step(\d+)$/i.exec(nodeId.trim());
  if (!m) return null;
  const n = parseInt(m[1], 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

const progressDenominator = computed(() => {
  const nodes = schema.value?.nodes ?? [];
  if (!nodes.length) return 1;
  const ordinals = nodes
    .map((n) => parseStepOrdinalFromId(n.id))
    .filter((x): x is number => x != null);
  const maxOrd = ordinals.length ? Math.max(...ordinals) : 0;
  return Math.max(maxOrd, nodes.length, 1);
});

const progressStepDisplay = computed(() => {
  const id = currentNodeId.value;
  const nodes = schema.value?.nodes ?? [];
  if (!id || !nodes.length) return 1;
  const parsed = parseStepOrdinalFromId(id);
  if (parsed != null) return parsed;
  const idx = nodes.findIndex((n) => n.id === id);
  if (idx >= 0) return idx + 1;
  return Math.max(1, navStack.value.length);
});

const progressPercent = computed(() => {
  const t = progressDenominator.value;
  const cur = progressStepDisplay.value;
  if (!t) return 0;
  const p = Math.round((cur / t) * 100);
  return Math.min(100, Math.max(0, p));
});

function stepKey(): string {
  return currentNodeId.value ?? "init";
}

async function emitView(): Promise<void> {
  await trackEvent(sessionId, "step_view", stepKey());
}

function onBeforeUnload(): void {
  void trackEvent(sessionId, "step_drop", stepKey());
}

watch(currentNodeId, () => {
  void emitView();
});

async function loadSchema(): Promise<void> {
  schemaLoading.value = true;
  schemaError.value = "";
  flowError.value = "";
  try {
    const row = await api<QuizSchemaApiRow>("/quiz-schema");
    const s = asSchema(row.schema);
    if (!s?.nodes?.length) {
      schemaError.value = "Схема квиза пуста";
      schemaRaw.value = null;
      schemaFp.value = "";
      return;
    }
    schemaRaw.value = s;
    const fp = fingerprint(s);
    schemaFp.value = fp;
    if (persistedSnap?.fingerprint === fp) {
      navStack.value = [...persistedSnap.navStack];
      stepsCompleted.value = [...persistedSnap.steps];
      answersByNode.value = { ...persistedSnap.answersByNode };
      form.value = { ...persistedSnap.form };
      aiSummary.value = persistedSnap.aiSummary;
    } else {
      const start = findStartNodeId(s);
      if (!start) {
        schemaError.value = "Не удалось определить начало квиза";
        return;
      }
      navStack.value = [start];
      stepsCompleted.value = [];
      answersByNode.value = {};
      form.value = defaultForm();
      aiSummary.value = "";
    }
  } catch (e) {
    schemaError.value = e instanceof Error ? e.message : "Не удалось загрузить квиз";
    schemaRaw.value = null;
    schemaFp.value = "";
  } finally {
    schemaLoading.value = false;
  }
}

/** Шаги для preview-summary: сначала журнал прохождения, иначе сборка из navStack + ответов (рассинхрон localStorage). */
function buildPreviewStepPayload(): {
  id: string;
  title: string;
  value: string | number | string[];
  blockType?: string;
}[] {
  const mapped = stepsCompleted.value.map((x) => ({
    id: x.nodeId,
    title: x.title,
    value: x.value,
    blockType: x.blockType,
  }));
  if (mapped.length > 0) return mapped;

  const s = schemaRaw.value;
  const cur = currentNodeId.value;
  if (!s || !cur) return [];

  const ids = navStack.value.filter((nid) => nid !== cur);
  const out: {
    id: string;
    title: string;
    value: string | number | string[];
    blockType?: string;
  }[] = [];

  for (const nid of ids) {
    const n = nodeById(s, nid);
    if (!n || n.type === "form" || n.type === "ai_summary") continue;
    const v = answersByNode.value[nid];
    if (v === undefined) continue;
    let value: string | number | string[] = v as string | number | string[];
    if (n.type === "slider" && typeof v === "number") value = `${v} м²`;
    out.push({
      id: nid,
      title: n.title ?? nid,
      value,
      blockType: n.type,
    });
  }
  return out;
}

watch(
  () => ({ cid: currentNodeId.value, steps: stepsCompleted.value }),
  async () => {
    await nextTick();
    if (currentNode.value?.type === "ai_summary") void loadSummary();
  },
  { deep: true },
);

async function loadSummary(): Promise<void> {
  summaryLoading.value = true;
  try {
    const body = {
      answers: {
        steps: buildPreviewStepPayload(),
      },
    };
    const res = await api<{ summary: string }>("/leads/preview-summary", {
      method: "POST",
      json: body,
    });
    aiSummary.value = res.summary;
  } catch {
    aiSummary.value = "Не удалось загрузить резюме. Продолжите к контактам.";
  } finally {
    summaryLoading.value = false;
  }
}

function pushStep(node: QuizNode, value: string | number | string[]): void {
  const prev = stepsCompleted.value;
  const last = prev[prev.length - 1];
  const entry: QuizStepEntry = {
    nodeId: node.id,
    title: node.title ?? node.id,
    value,
    blockType: node.type,
  };
  if (last?.nodeId === node.id) {
    stepsCompleted.value = [...prev.slice(0, -1), entry];
  } else {
    stepsCompleted.value = [...prev, entry];
  }
}

function advanceTo(nextId: string | null): void {
  flowError.value = "";
  if (!nextId) {
    flowError.value = "Для этого шага не задан следующий. Проверьте схему в админке.";
    return;
  }
  if (nextId === "done") {
    flowError.value = "Некорректная схема: шаг «done» не используется как экран. Обратитесь к администратору.";
    return;
  }
  const s = schemaRaw.value;
  if (!s || !nodeById(s, nextId)) {
    flowError.value = "Следующий блок не найден в схеме.";
    return;
  }
  navStack.value = [...navStack.value, nextId];
}

function onSelectSingle(node: QuizNode, opt: QuizOption): void {
  const s = schemaRaw.value;
  if (!s) return;
  answersByNode.value = { ...answersByNode.value, [node.id]: opt.label };
  pushStep(node, opt.label);
  const next = resolveNext(s, node, opt);
  advanceTo(next);
}

const multiDraft = ref<string[]>([]);

watch(
  () => currentNode.value,
  (node) => {
    if (!node || node.type !== "multi") return;
    const saved = answersByNode.value[node.id];
    if (Array.isArray(saved)) multiDraft.value = [...saved];
    else multiDraft.value = [];
  },
  { immediate: true },
);

function toggleMulti(opt: QuizOption): void {
  const id = opt.id;
  const label = opt.label;
  let next = [...multiDraft.value];
  if (id === "all") {
    next = [label];
  } else {
    next = next.filter((x) => x !== "Полностью всё");
    const idx = next.indexOf(label);
    if (idx >= 0) next.splice(idx, 1);
    else next.push(label);
  }
  multiDraft.value = next;
}

function multiChecked(label: string): boolean {
  return multiDraft.value.includes(label);
}

function commitMulti(node: QuizNode): void {
  const s = schemaRaw.value;
  if (!s || !multiDraft.value.length) return;
  answersByNode.value = { ...answersByNode.value, [node.id]: [...multiDraft.value] };
  pushStep(node, [...multiDraft.value]);
  const next = resolveNext(s, node);
  advanceTo(next);
}

const sliderDraft = ref(60);

watch(
  () => currentNode.value,
  (node) => {
    if (!node || node.type !== "slider") return;
    const saved = answersByNode.value[node.id];
    if (typeof saved === "number") sliderDraft.value = saved;
    else sliderDraft.value = node.default ?? node.min ?? 20;
  },
  { immediate: true },
);

function commitSlider(node: QuizNode): void {
  const s = schemaRaw.value;
  if (!s) return;
  const v = sliderDraft.value;
  answersByNode.value = { ...answersByNode.value, [node.id]: v };
  pushStep(node, `${v} м²`);
  const next = resolveNext(s, node);
  advanceTo(next);
}

function commitAiSummary(node: QuizNode): void {
  const s = schemaRaw.value;
  if (!s) return;
  pushStep(node, aiSummary.value);
  const next = resolveNext(s, node);
  advanceTo(next);
}

function goBack(): void {
  if (navStack.value.length <= 1) return;
  navStack.value = navStack.value.slice(0, -1);
  stepsCompleted.value = stepsCompleted.value.slice(0, -1);
  flowError.value = "";
}

const phoneDisplay = computed(() => {
  const d = form.value.phoneDigits.replace(/\D/g, "").slice(0, 10);
  const p = (i: number) => d[i] ?? "_";
  if (!d.length) return "+7 ";
  return `+7 (${p(0)}${p(1)}${p(2)}) ${p(3)}${p(4)}${p(5)}-${p(6)}${p(7)}-${p(8)}${p(9)}`;
});

const phoneValid = computed(() => form.value.phoneDigits.replace(/\D/g, "").length === 10);

function onPhoneInput(e: Event): void {
  const t = e.target as HTMLInputElement;
  const digits = t.value.replace(/\D/g, "");
  const rest = digits.startsWith("7") ? digits.slice(1) : digits.startsWith("8") ? digits.slice(1) : digits;
  form.value.phoneDigits = rest.slice(0, 10);
}

function formatPhoneApi(): string {
  const d = form.value.phoneDigits.replace(/\D/g, "").slice(0, 10);
  return `+7${d}`;
}

const submitLoading = ref(false);
const submitError = ref("");
const requestNumber = ref("");
const qrDataUrl = ref("");

async function submitLead(): Promise<void> {
  submitError.value = "";
  if (!form.value.consent) {
    submitError.value = "Нужно согласие на обработку данных";
    return;
  }
  if (!phoneValid.value) {
    submitError.value = "Введите корректный номер телефона";
    return;
  }
  submitLoading.value = true;
  try {
    const snapshot = JSON.parse(JSON.stringify(stepsCompleted.value)) as QuizStepEntry[];
    const stepPayload = snapshot.map((x) => ({
      id: x.nodeId,
      title: x.title,
      value: x.value,
      blockType: x.blockType,
    }));
    const answers: Record<string, unknown> = { steps: stepPayload };
    for (const s of stepPayload) {
      const sid = String(s.id ?? "");
      const tit = String(s.title ?? "").toLowerCase();
      if (sid === "step1" || tit.includes("помещ")) answers.room_type = s.value;
      if (sid === "step2" || tit.includes("зон")) answers.zones = s.value;
      if (sid === "step3" || tit.includes("площад")) {
        const m = typeof s.value === "string" ? s.value.match(/(\d+)/) : null;
        if (m) answers.area_sqm = Number(m[1]);
      }
      if (sid === "step4" || tit.includes("стил")) answers.style = s.value;
      if (sid === "step5" || tit.includes("бюджет")) answers.budget = s.value;
    }
    const payload = {
      name: form.value.name.trim(),
      phone: formatPhoneApi(),
      email: form.value.email.trim() || null,
      comment: form.value.comment.trim() || null,
      consent: form.value.consent,
      session_id: sessionId,
      answers,
    };
    const res = await api<{ id: string; request_number: string }>("/leads", {
      method: "POST",
      json: payload,
    });
    requestNumber.value = res.request_number;
    const url = `${window.location.origin}/lead/${res.id}`;
    qrDataUrl.value = await QRCode.toDataURL(url, {
      width: 220,
      margin: 2,
      color: { dark: "#1a1b20", light: "#ffffff" },
    });
    successDone.value = true;
    clearPersisted();
  } catch (e) {
    submitError.value = e instanceof Error ? e.message : "Ошибка отправки";
  } finally {
    submitLoading.value = false;
  }
}

const canProceed = computed(() => {
  const node = currentNode.value;
  if (!node) return false;
  switch (node.type) {
    case "multi":
      return multiDraft.value.length > 0;
    case "slider":
      return true;
    case "ai_summary":
      return !summaryLoading.value;
    default:
      return false;
  }
});

function onNextClick(): void {
  const node = currentNode.value;
  if (!node) return;
  if (node.type === "multi") commitMulti(node);
  else if (node.type === "slider") commitSlider(node);
  else if (node.type === "ai_summary") commitAiSummary(node);
}

function showFooterNext(): boolean {
  const t = currentNode.value?.type;
  return t === "multi" || t === "slider" || t === "ai_summary";
}

function imgKey(nodeId: string, optId: string): string {
  return `${nodeId}:${optId}`;
}

function onImgError(nodeId: string, optId: string): void {
  const k = imgKey(nodeId, optId);
  imgError.value = { ...imgError.value, [k]: true };
}

onMounted(() => {
  void emitView();
  window.addEventListener("beforeunload", onBeforeUnload);
  void loadSchema();
});

onUnmounted(() => {
  window.removeEventListener("beforeunload", onBeforeUnload);
});
</script>

<template>
  <div class="min-h-screen bg-gradient-to-b from-ink-50 via-white to-ink-100">
    <header class="border-b border-ink-200/60 bg-white/80 backdrop-blur-md">
      <div class="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
        <div>
          <p class="font-display text-lg font-semibold tracking-tight text-ink-950">Студия интерьера</p>
          <p class="text-sm text-ink-800/70">Подбор проекта за пару минут</p>
        </div>
        <div class="text-right text-sm text-ink-800/80">
          <span class="font-medium text-accent-dim">Консультация</span>
          <span class="block text-xs">без обязательств</span>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-3xl px-4 py-8">
      <div v-if="schemaLoading" class="rounded-2xl border border-ink-200 bg-white p-10 text-center text-ink-700 shadow-card">
        Загружаем квиз…
      </div>

      <div v-else-if="schemaError" class="rounded-2xl border border-red-200 bg-red-50/80 p-6 text-red-800 shadow-card">
        {{ schemaError }}
      </div>

      <template v-else-if="!successDone && currentNode">
        <div class="mb-8">
          <div class="mb-2 flex justify-between text-sm text-ink-800/80">
            <span>Прогресс</span>
            <span>Шаг {{ progressStepDisplay }} из {{ progressDenominator }}</span>
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-ink-200">
            <div
              class="h-full rounded-full bg-gradient-to-r from-accent-dim to-accent transition-all duration-500 ease-out"
              :style="{ width: progressPercent + '%' }"
            />
          </div>
        </div>

        <p v-if="flowError" class="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          {{ flowError }}
        </p>

        <div class="quiz-perspective">
          <Transition name="slide3d" mode="out-in">
            <div :key="currentNode.id" class="quiz-stage">
              <!-- single -->
              <section v-if="currentNode.type === 'single'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 md:text-3xl">
                  {{ currentNode.title || "Выберите вариант" }}
                </h1>
                <p class="text-ink-800/80">Выберите один вариант</p>
                <div class="grid gap-3 sm:grid-cols-2">
                  <button
                    v-for="opt in currentNode.options || []"
                    :key="opt.id"
                    type="button"
                    class="overflow-hidden rounded-2xl border-2 text-left shadow-card transition hover:shadow-lift"
                    :class="
                      answersByNode[currentNode.id] === opt.label
                        ? 'border-accent bg-amber-50/80'
                        : 'border-transparent bg-white hover:border-ink-200'
                    "
                    @click="onSelectSingle(currentNode, opt)"
                  >
                    <div
                      v-if="opt.image && !imgError[imgKey(currentNode.id, opt.id)]"
                      class="relative h-28 w-full overflow-hidden bg-ink-100"
                    >
                      <img
                        :src="opt.image"
                        :alt="opt.label"
                        class="h-full w-full object-cover"
                        @error="onImgError(currentNode.id, opt.id)"
                      />
                      <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                      <div class="absolute bottom-3 left-3 right-3">
                        <span class="font-medium text-white drop-shadow">{{ opt.label }}</span>
                      </div>
                    </div>
                    <div v-else class="p-4">
                      <span class="font-medium text-ink-900">{{ opt.label }}</span>
                    </div>
                  </button>
                </div>
              </section>

              <!-- multi -->
              <section v-else-if="currentNode.type === 'multi'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 md:text-3xl">
                  {{ currentNode.title || "Выбор" }}
                </h1>
                <p class="text-ink-800/80">Можно выбрать несколько</p>
                <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  <label
                    v-for="opt in currentNode.options || []"
                    :key="opt.id"
                    class="flex cursor-pointer items-center gap-2 rounded-xl border bg-white p-3 shadow-card transition hover:border-accent/40"
                    :class="multiChecked(opt.label) ? 'border-accent ring-1 ring-accent/30' : 'border-ink-100'"
                  >
                    <input
                      type="checkbox"
                      class="size-4 accent-accent"
                      :checked="multiChecked(opt.label)"
                      @click.prevent="toggleMulti(opt)"
                    />
                    <span class="text-sm font-medium text-ink-900">{{ opt.label }}</span>
                  </label>
                </div>
              </section>

              <!-- slider -->
              <section v-else-if="currentNode.type === 'slider'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 md:text-3xl">
                  {{ currentNode.title || "Значение" }}
                </h1>
                <div class="rounded-2xl bg-white p-6 shadow-card">
                  <p class="mb-4 text-center font-display text-3xl font-semibold text-accent-dim">{{ sliderDraft }} м²</p>
                  <input
                    v-model.number="sliderDraft"
                    type="range"
                    :min="currentNode.min ?? 0"
                    :max="currentNode.max ?? 100"
                    :step="currentNode.step ?? 1"
                    class="w-full accent-accent"
                  />
                  <div class="mt-2 flex justify-between text-xs text-ink-800/60">
                    <span>{{ currentNode.min ?? 0 }}</span>
                    <span>{{ currentNode.max ?? 100 }}</span>
                  </div>
                </div>
              </section>

              <!-- ai_summary -->
              <section v-else-if="currentNode.type === 'ai_summary'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 md:text-3xl">
                  {{ currentNode.title || "Резюме" }}
                </h1>
                <p class="text-ink-800/80">На основе ваших ответов</p>
                <div class="rounded-2xl border border-ink-200 bg-white p-6 shadow-lift">
                  <p v-if="summaryLoading" class="text-ink-800/70">Готовим текст…</p>
                  <p v-else class="leading-relaxed text-ink-900">{{ aiSummary }}</p>
                </div>
              </section>

              <!-- form -->
              <section v-else-if="currentNode.type === 'form'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 md:text-3xl">
                  {{ currentNode.title || "Контакты" }}
                </h1>
                <div class="space-y-4 rounded-2xl bg-white p-6 shadow-card">
                  <label class="block text-sm font-medium text-ink-800">
                    Имя
                    <input
                      v-model="form.name"
                      type="text"
                      class="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 outline-none focus:border-accent"
                      autocomplete="name"
                    />
                  </label>
                  <label class="block text-sm font-medium text-ink-800">
                    Телефон <span class="text-red-600">*</span>
                    <input
                      :value="phoneDisplay"
                      type="text"
                      inputmode="tel"
                      placeholder="+7 (___) ___-__-__"
                      class="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 font-mono outline-none focus:border-accent"
                      @input="onPhoneInput"
                    />
                  </label>
                  <label class="block text-sm font-medium text-ink-800">
                    Email
                    <input
                      v-model="form.email"
                      type="email"
                      class="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 outline-none focus:border-accent"
                      autocomplete="email"
                    />
                  </label>
                  <label class="block text-sm font-medium text-ink-800">
                    Комментарий
                    <textarea
                      v-model="form.comment"
                      rows="3"
                      class="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 outline-none focus:border-accent"
                    />
                  </label>
                  <label class="flex items-start gap-2 text-sm text-ink-800">
                    <input v-model="form.consent" type="checkbox" class="mt-1 accent-accent" />
                    <span>Согласен на обработку персональных данных</span>
                  </label>
                  <p v-if="submitError" class="text-sm text-red-600">{{ submitError }}</p>
                  <button
                    type="button"
                    class="w-full rounded-xl bg-ink-950 py-3 font-semibold text-white transition hover:bg-ink-900 disabled:opacity-50"
                    :disabled="submitLoading"
                    @click="submitLead"
                  >
                    {{ submitLoading ? "Отправка…" : "Получить консультацию" }}
                  </button>
                </div>
              </section>

              <section v-else class="space-y-4 rounded-2xl border border-ink-200 bg-white p-6 shadow-card">
                <p class="text-ink-800">
                  Тип блока «<strong>{{ currentNode.type }}</strong>» пока не поддерживается на публичной странице.
                </p>
              </section>
            </div>
          </Transition>
        </div>

        <div v-if="showFooterNext()" class="mt-10 flex items-center justify-between gap-4">
          <button
            type="button"
            class="rounded-xl border border-ink-200 bg-white px-5 py-2.5 text-sm font-medium text-ink-900 transition hover:bg-ink-50 disabled:opacity-40"
            :disabled="navStack.length <= 1"
            @click="goBack"
          >
            Назад
          </button>
          <button
            type="button"
            class="rounded-xl bg-ink-950 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-ink-900 disabled:opacity-40"
            :disabled="!canProceed"
            @click="onNextClick"
          >
            Далее
          </button>
        </div>

        <div v-else-if="currentNode.type === 'single'" class="mt-10 flex justify-start">
          <button
            type="button"
            class="rounded-xl border border-ink-200 bg-white px-5 py-2.5 text-sm font-medium text-ink-900 hover:bg-ink-50 disabled:opacity-40"
            :disabled="navStack.length <= 1"
            @click="goBack"
          >
            Назад
          </button>
        </div>

        <div v-else-if="currentNode.type === 'form'" class="mt-6 flex justify-start">
          <button
            type="button"
            class="rounded-xl border border-ink-200 bg-white px-5 py-2.5 text-sm font-medium text-ink-900 hover:bg-ink-50"
            :disabled="navStack.length <= 1"
            @click="goBack"
          >
            Назад
          </button>
        </div>
      </template>

      <section v-else-if="successDone" class="space-y-8 text-center">
        <div class="mx-auto max-w-md rounded-3xl border border-ink-200 bg-white p-8 shadow-lift">
          <p class="text-sm font-medium uppercase tracking-wider text-accent-dim">Заявка принята</p>
          <h1 class="mt-2 font-display text-3xl font-semibold text-ink-950">Спасибо!</h1>
          <p class="mt-2 text-ink-800/80">Номер заявки</p>
          <p class="mt-1 font-mono text-2xl font-bold text-ink-950">{{ requestNumber }}</p>
          <div class="mt-6 flex justify-center">
            <img v-if="qrDataUrl" :src="qrDataUrl" alt="QR" class="rounded-xl border border-ink-100" />
          </div>
          <p class="mt-4 text-sm text-ink-800/70">Отсканируйте QR, чтобы отслеживать статус заявки</p>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.slide3d-enter-active,
.slide3d-leave-active {
  transition:
    transform 0.45s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.35s ease;
}
.slide3d-enter-from {
  opacity: 0;
  transform: translateX(48px) rotateY(-14deg);
}
.slide3d-leave-to {
  opacity: 0;
  transform: translateX(-48px) rotateY(14deg);
}
</style>
