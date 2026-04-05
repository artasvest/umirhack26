<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import QRCode from "qrcode";
import { api } from "@/api/client";
import type { QuizNode, QuizOption, QuizSchema } from "@/types/quiz-schema";
import { rotateSessionId, useSessionId } from "@/composables/useSessionId";
import {
  clearPersisted,
  loadPersisted,
  watchPersistSchema,
  type QuizFormState,
  type QuizStepEntry,
} from "@/composables/useQuizPersistence";
import { trackEvent } from "@/composables/trackAnalytics";
import {
  extractRuMobileDigits,
  formatRuPhoneDisplay,
  isRuPhoneComplete,
  ruPhoneToE164,
} from "@/composables/useRuPhoneMask";
import {
  loadLastSubmittedLead,
  saveLastSubmittedLead,
  type LastSubmittedLead,
} from "@/composables/useLastSubmittedLead";

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

const ANALYTICS_VIEWS_KEY = "studio_analytics_step_views_v1";

function readStoredStepViews(sid: string, fp: string): Set<string> {
  try {
    const raw = sessionStorage.getItem(ANALYTICS_VIEWS_KEY);
    if (!raw) return new Set();
    const o = JSON.parse(raw) as { sessionId?: string; fingerprint?: string; keys?: string[] };
    if (o.sessionId !== sid || o.fingerprint !== fp) return new Set();
    return new Set(Array.isArray(o.keys) ? o.keys : []);
  } catch {
    return new Set();
  }
}

function writeStoredStepViews(sid: string, fp: string, keys: Set<string>): void {
  try {
    sessionStorage.setItem(
      ANALYTICS_VIEWS_KEY,
      JSON.stringify({ sessionId: sid, fingerprint: fp, keys: [...keys] }),
    );
  } catch {
    /* ignore quota */
  }
}

/** Уже отправленные step_view за эту вкладку (sessionStorage + смена схемы сбрасывает). */
let stepViewSentKeys = new Set<string>();

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

/** Все возможные следующие узлы (как в схеме) — для оценки оставшегося пути. */
function outgoingTargets(schema: QuizSchema, node: QuizNode): string[] {
  const out = new Set<string>();
  for (const e of schema.edges ?? []) {
    if (e.from === node.id) out.add(e.to);
  }
  if (node.type === "single" && node.options?.length) {
    for (const o of node.options) {
      if (o.nextStep) out.add(o.nextStep);
    }
  }
  if (node.nextStep) out.add(node.nextStep);
  return [...out];
}

/**
 * Сколько экранов осталось пройти после `fromId` до формы контактов по кратчайшему пути.
 * Учитывается сам экран form (последний шаг квиза). Блок ИИ-резюме (ai_summary) — обычный экран, не вырезается.
 */
function countScreensToFormShortestAfter(schema: QuizSchema, fromId: string): number {
  const fromNode = nodeById(schema, fromId);
  if (!fromNode || fromNode.type === "form") return 0;

  const q: string[] = [fromId];
  const parent = new Map<string, string | null>();
  parent.set(fromId, null);
  let formReach: string | null = null;

  while (q.length) {
    const u = q.shift()!;
    const nu = nodeById(schema, u);
    if (nu?.type === "form") {
      formReach = u;
      break;
    }
    const nodeU = nodeById(schema, u);
    if (!nodeU) continue;
    for (const v of outgoingTargets(schema, nodeU)) {
      if (!parent.has(v)) {
        parent.set(v, u);
        q.push(v);
      }
    }
  }

  if (!formReach) return 0;

  const path: string[] = [];
  let x: string | null = formReach;
  while (x != null) {
    path.push(x);
    x = parent.get(x) ?? null;
  }
  path.reverse();
  return Math.max(0, path.length - 1);
}

/** Макс. число экранов после `fromId` до form по самому длинному пути (form считается; ai_summary — тоже). */
function countScreensToFormLongestAfter(schema: QuizSchema, fromId: string): number {
  const fromNode = nodeById(schema, fromId);
  if (!fromNode || fromNode.type === "form") return 0;

  const memo = new Map<string, number>();

  function dfs(u: string, visiting: Set<string>): number {
    const hit = memo.get(u);
    if (hit !== undefined) return hit;
    if (visiting.has(u)) return 0;
    const nu = nodeById(schema, u);
    if (!nu || nu.type === "form") return 0;

    visiting.add(u);
    let best = 0;
    for (const v of outgoingTargets(schema, nu)) {
      const nv = nodeById(schema, v);
      if (!nv) continue;
      const add = nv.type === "form" ? 1 : 1 + dfs(v, visiting);
      best = Math.max(best, add);
    }
    visiting.delete(u);
    memo.set(u, best);
    return best;
  }

  return dfs(fromId, new Set());
}

let sessionId = useSessionId();
const persistedSnap = loadPersisted();

const schemaRaw = ref<QuizSchema | null>(null);
const schemaLoading = ref(true);
const schemaError = ref("");
const flowError = ref("");
const successDone = ref(false);
/** Последняя отправленная заявка в этом браузере — ссылка в шапке без повторного сканирования QR */
const lastSubmittedLead = ref<LastSubmittedLead | null>(null);

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
/** id строки quiz_schema с сервера (для аналитики и заявки); 0 = нет привязки */
const quizSchemaRowId = ref<number | null>(null);

const schema = computed(() => schemaRaw.value);

watchPersistSchema(schemaFp, navStack, stepsCompleted, answersByNode, form, aiSummary);

const currentNodeId = computed(() => navStack.value[navStack.value.length - 1] ?? null);

const currentNode = computed((): QuizNode | null => {
  const s = schema.value;
  const id = currentNodeId.value;
  if (!s || !id) return null;
  return nodeById(s, id) ?? null;
});

/** Текущий шаг = сколько экранов уже открыли по пути. */
const progressStepDisplay = computed(() => Math.max(1, navStack.value.length));

/**
 * Знаменатель = число экранов от старта до формы включительно (вопросы + ai_summary + form).
 * На короткой ветке — «пройдено + кратчайший остаток до form», если до длиннейшего пути уже не дотянуть.
 */
const progressDenominator = computed(() => {
  const s = schema.value;
  const id = currentNodeId.value;
  const depth = Math.max(1, navStack.value.length);
  if (!s || !id) return depth;
  const start = findStartNodeId(s);
  if (!start) return depth;

  const longestFromStart = Math.max(1, 1 + countScreensToFormLongestAfter(s, start));
  const minTotal = depth + countScreensToFormShortestAfter(s, id);
  const maxStillPossible = depth + countScreensToFormLongestAfter(s, id);

  if (maxStillPossible < longestFromStart) return Math.max(1, minTotal);
  return longestFromStart;
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

/** Ответы по узлам строго выше `curNodeId` в текущем navStack (как контекст ветки). */
function ancestorAnswersBeforeNode(curNodeId: string): Record<string, unknown> {
  const ids = navStack.value;
  const idx = ids.lastIndexOf(curNodeId);
  if (idx < 0) return {};
  const anc: Record<string, unknown> = {};
  for (let i = 0; i < idx; i++) {
    const id = ids[i]!;
    if (id in answersByNode.value) anc[id] = answersByNode.value[id];
  }
  return anc;
}

/**
 * Один step_view на шаг (step_key) за сессию вкладки и версию схемы: назад/смена ответа/F5
 * не раздувают просмотры. Множество шагов хранится в sessionStorage.
 */
async function emitView(): Promise<void> {
  const k = stepKey();
  const fp = schemaFp.value;
  if (!fp || !k || k === "init") return;
  if (stepViewSentKeys.has(k)) return;
  stepViewSentKeys.add(k);
  writeStoredStepViews(sessionId, fp, stepViewSentKeys);
  await trackEvent(sessionId, "step_view", k, undefined, quizSchemaRowId.value);
}

const stepAnswerDedupeKeys = new Set<string>();

function stepAnswerDedupeKey(nodeId: string, value: string | number | string[]): string {
  const idx = navStack.value.lastIndexOf(nodeId);
  const v = Array.isArray(value)
    ? [...value].sort((a, b) => String(a).localeCompare(String(b), "ru"))
    : value;
  if (idx < 0) return JSON.stringify({ c: nodeId, v, o: "orphan" });
  return JSON.stringify({ c: nodeId, a: ancestorAnswersBeforeNode(nodeId), v });
}

function trackStepAnswer(node: QuizNode, value: string | number | string[]): void {
  const bt = node.type;
  if (bt === "form" || bt === "ai_summary") return;
  const dk = stepAnswerDedupeKey(node.id, value);
  if (stepAnswerDedupeKeys.has(dk)) return;
  stepAnswerDedupeKeys.add(dk);
  const payload: Record<string, unknown> = { block_type: bt };
  if (Array.isArray(value)) payload.values = value;
  else payload.value = typeof value === "number" ? String(value) : value;
  void trackEvent(sessionId, "step_answer", node.id, payload, quizSchemaRowId.value);
}

/** Дропы считаются на сервере: сессия без заявки и без активности N минут (см. analytics_sessions). */

watch(currentNodeId, () => {
  void emitView();
});

async function loadSchema(): Promise<void> {
  schemaLoading.value = true;
  schemaError.value = "";
  flowError.value = "";
  try {
    const row = await api<QuizSchemaApiRow>("/quiz-schema");
    quizSchemaRowId.value = row.id > 0 ? row.id : null;
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
      stepViewSentKeys = readStoredStepViews(sessionId, fp);
      navStack.value = [...persistedSnap.navStack];
      stepsCompleted.value = [...persistedSnap.steps];
      answersByNode.value = { ...persistedSnap.answersByNode };
      form.value = { ...persistedSnap.form };
      aiSummary.value = persistedSnap.aiSummary;
    } else {
      stepViewSentKeys = new Set();
      writeStoredStepViews(sessionId, fp, stepViewSentKeys);
      stepAnswerDedupeKeys.clear();
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
    quizSchemaRowId.value = null;
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
  // Маркер конца (см. default_quiz_schema: у form в nextStep), не узел на графе.
  if (nextId === "done" || nextId === "end" || nextId === "finish") {
    flowError.value = "";
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
  trackStepAnswer(node, opt.label);
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
  const chosen = [...multiDraft.value];
  pushStep(node, chosen);
  trackStepAnswer(node, chosen);
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
  const label = `${v} м²`;
  pushStep(node, label);
  trackStepAnswer(node, label);
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

const phoneDisplay = computed(() => formatRuPhoneDisplay(form.value.phoneDigits));

const phoneValid = computed(() => isRuPhoneComplete(form.value.phoneDigits));

function onPhoneInput(e: Event): void {
  const t = e.target as HTMLInputElement;
  form.value.phoneDigits = extractRuMobileDigits(t.value);
}

function onPhonePaste(e: ClipboardEvent): void {
  e.preventDefault();
  const text = e.clipboardData?.getData("text") ?? "";
  form.value.phoneDigits = extractRuMobileDigits(text);
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
    submitError.value = "Введите полный номер: +7 и 10 цифр мобильного телефона.";
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
    const href = window.location.href.split("#")[0];
    const utm =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("utm_source")
        : null;
    const payload: Record<string, unknown> = {
      name: form.value.name.trim(),
      phone: ruPhoneToE164(form.value.phoneDigits),
      email: form.value.email.trim() || null,
      comment: form.value.comment.trim() || null,
      consent: form.value.consent,
      session_id: sessionId,
      answers,
      page_url: href || null,
      utm_source: utm && utm.trim() ? utm.trim().slice(0, 256) : null,
    };
    if (quizSchemaRowId.value != null && quizSchemaRowId.value > 0) {
      payload.quiz_schema_id = quizSchemaRowId.value;
    }
    const res = await api<{
      id: string;
      request_number: string;
      page_url?: string | null;
      utm_source?: string | null;
    }>("/leads", {
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
    saveLastSubmittedLead(res.id, res.request_number);
    lastSubmittedLead.value = loadLastSubmittedLead();
    /** Заявка уже привязана к старому session_id в теле POST; дальше — новая «сессия» воронки. */
    sessionId = rotateSessionId();
    stepViewSentKeys = new Set();
    stepAnswerDedupeKeys.clear();
    if (schemaFp.value) writeStoredStepViews(sessionId, schemaFp.value, stepViewSentKeys);
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
  lastSubmittedLead.value = loadLastSubmittedLead();
  void emitView();
  void loadSchema();
});

</script>

<template>
  <div class="page-shell">
    <header class="app-header">
      <div class="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div class="min-w-0">
          <p class="font-display text-lg font-bold tracking-tight text-ink-950 dark:text-ink-50 sm:text-xl">
            Студия интерьера
          </p>
          <p class="mt-0.5 text-sm text-ink-600 dark:text-ink-400">Подбор проекта за пару минут</p>
        </div>
        <div class="flex flex-wrap items-center gap-2 sm:justify-end sm:gap-3">
          <RouterLink
            v-if="lastSubmittedLead"
            :to="`/lead/${lastSubmittedLead.id}`"
            class="inline-flex min-h-10 items-center rounded-xl border border-accent/45 bg-amber-50/95 px-3 py-2 text-sm font-bold text-ink-950 shadow-sm ring-1 ring-accent/15 transition hover:border-accent hover:bg-amber-100/95 hover:shadow-md dark:border-accent/35 dark:bg-ink-800 dark:text-ink-50 dark:ring-accent/10 dark:hover:bg-ink-700"
          >
            Ваша заявка
            <span class="ml-1.5 font-mono text-xs font-bold text-accent-dim dark:text-accent-dim"
              >№{{ lastSubmittedLead.requestNumber }}</span
            >
          </RouterLink>
          <div class="text-left text-sm text-ink-700 dark:text-ink-300 sm:text-right">
            <span class="font-bold text-accent-dim">Консультация</span>
            <span class="block text-xs text-ink-600 dark:text-ink-500">без обязательств</span>
          </div>
        </div>
      </div>
    </header>

    <main class="content-narrow">
      <div
        v-if="schemaLoading"
        class="surface-panel p-10 text-center text-base font-medium text-ink-700 dark:text-ink-300"
      >
        Загружаем квиз…
      </div>

      <div
        v-else-if="schemaError"
        class="rounded-2xl border border-red-200 bg-red-50/90 p-6 text-red-800 shadow-card backdrop-blur-sm dark:border-red-900/50 dark:bg-red-950/35 dark:text-red-200 sm:rounded-3xl sm:p-8"
      >
        {{ schemaError }}
      </div>

      <template v-else-if="!successDone && currentNode">
        <div class="mb-8 sm:mb-10">
          <div class="mb-2 flex justify-between text-sm font-semibold text-ink-800 dark:text-ink-300">
            <span>Прогресс</span>
            <span class="tabular-nums">Шаг {{ progressStepDisplay }} из {{ progressDenominator }}</span>
          </div>
          <div class="h-2.5 overflow-hidden rounded-full bg-ink-200/90 shadow-inner dark:bg-ink-800 sm:h-3">
            <div
              class="h-full rounded-full bg-gradient-to-r from-accent-dim via-accent to-amber-300 shadow-sm transition-all duration-500 ease-out dark:to-accent"
              :style="{ width: progressPercent + '%' }"
            />
          </div>
        </div>

        <p
          v-if="flowError"
          class="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-700/50 dark:bg-amber-950/25 dark:text-amber-100"
        >
          {{ flowError }}
        </p>

        <div class="quiz-perspective">
          <Transition name="slide3d" mode="out-in">
            <div :key="currentNode.id" class="quiz-stage">
              <!-- single -->
              <section v-if="currentNode.type === 'single'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-ink-50 md:text-3xl">
                  {{ currentNode.title || "Выберите вариант" }}
                </h1>
                <p class="text-ink-800/80 dark:text-ink-300">Выберите один вариант</p>
                <div class="grid gap-3 sm:grid-cols-2">
                  <button
                    v-for="opt in currentNode.options || []"
                    :key="opt.id"
                    type="button"
                    class="overflow-hidden rounded-2xl border-2 text-left shadow-card transition hover:shadow-lift"
                    :class="
                      answersByNode[currentNode.id] === opt.label
                        ? 'border-accent bg-amber-50/80 dark:border-accent dark:bg-ink-800/80'
                        : 'border-transparent bg-white hover:border-ink-200 dark:bg-ink-900 dark:hover:border-ink-600'
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
                      <span class="font-medium text-ink-900 dark:text-ink-100">{{ opt.label }}</span>
                    </div>
                  </button>
                </div>
              </section>

              <!-- multi -->
              <section v-else-if="currentNode.type === 'multi'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-ink-50 md:text-3xl">
                  {{ currentNode.title || "Выбор" }}
                </h1>
                <p class="text-ink-800/80 dark:text-ink-300">Можно выбрать несколько</p>
                <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  <label
                    v-for="opt in currentNode.options || []"
                    :key="opt.id"
                    role="checkbox"
                    :aria-checked="multiChecked(opt.label)"
                    tabindex="0"
                    class="flex cursor-pointer items-center gap-2 rounded-xl border bg-white p-3 shadow-card outline-none transition hover:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/50 dark:bg-ink-900"
                    :class="
                      multiChecked(opt.label) ? 'border-accent ring-1 ring-accent/30 dark:border-accent' : 'border-ink-100 dark:border-ink-700'
                    "
                    @click.prevent="toggleMulti(opt)"
                    @keydown.space.prevent="toggleMulti(opt)"
                    @keydown.enter.prevent="toggleMulti(opt)"
                  >
                    <span
                      class="flex size-4 shrink-0 items-center justify-center rounded border-2 transition"
                      :class="
                        multiChecked(opt.label)
                          ? 'border-accent-dim bg-accent-dim'
                          : 'border-ink-300 bg-white dark:border-ink-600 dark:bg-ink-900'
                      "
                      aria-hidden="true"
                    >
                      <svg
                        v-show="multiChecked(opt.label)"
                        class="size-2.5 text-white"
                        viewBox="0 0 12 12"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <path
                          d="M2.5 6L5 8.5 9.5 3"
                          stroke="currentColor"
                          stroke-width="2"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </span>
                    <span class="text-sm font-medium text-ink-900 dark:text-ink-100">{{ opt.label }}</span>
                  </label>
                </div>
              </section>

              <!-- slider -->
              <section v-else-if="currentNode.type === 'slider'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-ink-50 md:text-3xl">
                  {{ currentNode.title || "Значение" }}
                </h1>
                <div class="rounded-2xl bg-white p-6 shadow-card dark:bg-ink-900 dark:ring-1 dark:ring-ink-700">
                  <p class="mb-4 text-center font-display text-3xl font-semibold text-accent-dim">{{ sliderDraft }} м²</p>
                  <input
                    v-model.number="sliderDraft"
                    type="range"
                    :min="currentNode.min ?? 0"
                    :max="currentNode.max ?? 100"
                    :step="currentNode.step ?? 1"
                    class="w-full accent-accent"
                  />
                  <div class="mt-2 flex justify-between text-xs text-ink-800/60 dark:text-ink-400">
                    <span>{{ currentNode.min ?? 0 }}</span>
                    <span>{{ currentNode.max ?? 100 }}</span>
                  </div>
                </div>
              </section>

              <!-- ai_summary -->
              <section v-else-if="currentNode.type === 'ai_summary'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-ink-50 md:text-3xl">
                  {{ currentNode.title || "Резюме" }}
                </h1>
                <p class="text-ink-800/80 dark:text-ink-300">На основе ваших ответов</p>
                <div class="rounded-2xl border border-ink-200 bg-white p-6 shadow-lift dark:border-ink-700 dark:bg-ink-900">
                  <p v-if="summaryLoading" class="text-ink-800/70 dark:text-ink-400">Готовим текст…</p>
                  <p v-else class="leading-relaxed text-ink-900 dark:text-ink-100">{{ aiSummary }}</p>
                </div>
              </section>

              <!-- form -->
              <section v-else-if="currentNode.type === 'form'" class="space-y-6">
                <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-ink-50 md:text-3xl">
                  {{ currentNode.title || "Контакты" }}
                </h1>
                <div class="space-y-4 rounded-2xl bg-white p-6 shadow-card dark:bg-ink-900 dark:ring-1 dark:ring-ink-700">
                  <label class="block text-sm font-medium text-ink-800 dark:text-ink-200">
                    Имя
                    <input
                      v-model="form.name"
                      type="text"
                      class="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 outline-none focus:border-accent dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50"
                      autocomplete="name"
                    />
                  </label>
                  <label class="block text-sm font-medium text-ink-800 dark:text-ink-200">
                    Телефон <span class="text-red-600 dark:text-red-400">*</span>
                    <input
                      :value="phoneDisplay"
                      type="text"
                      inputmode="numeric"
                      autocomplete="tel"
                      maxlength="18"
                      placeholder="+7 (900) 123-45-67"
                      aria-describedby="quiz-phone-hint"
                      class="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 font-mono text-base tracking-wide outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50"
                      @input="onPhoneInput"
                      @paste="onPhonePaste"
                    />
                    <span id="quiz-phone-hint" class="mt-1 block text-xs text-ink-600 dark:text-ink-400">
                      Российский мобильный: можно вставить номер целиком — маска подставится сама.
                    </span>
                  </label>
                  <label class="block text-sm font-medium text-ink-800 dark:text-ink-200">
                    Email
                    <input
                      v-model="form.email"
                      type="email"
                      class="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 outline-none focus:border-accent dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50"
                      autocomplete="email"
                    />
                  </label>
                  <label class="block text-sm font-medium text-ink-800 dark:text-ink-200">
                    Комментарий
                    <textarea
                      v-model="form.comment"
                      rows="3"
                      class="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 outline-none focus:border-accent dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50"
                    />
                  </label>
                  <label class="flex cursor-pointer items-start gap-2 text-sm text-ink-800 dark:text-ink-200">
                    <input v-model="form.consent" type="checkbox" class="peer sr-only" />
                    <span
                      class="mt-1 flex size-4 shrink-0 items-center justify-center rounded border-2 transition peer-focus-visible:ring-2 peer-focus-visible:ring-accent/50"
                      :class="
                        form.consent ? 'border-accent-dim bg-accent-dim' : 'border-ink-300 bg-white dark:border-ink-600 dark:bg-ink-900'
                      "
                      aria-hidden="true"
                    >
                      <svg
                        v-show="form.consent"
                        class="size-2.5 text-white"
                        viewBox="0 0 12 12"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <path
                          d="M2.5 6L5 8.5 9.5 3"
                          stroke="currentColor"
                          stroke-width="2"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </span>
                    <span>Согласен на обработку персональных данных</span>
                  </label>
                  <p v-if="submitError" class="text-sm text-red-600 dark:text-red-400">{{ submitError }}</p>
                  <button
                    type="button"
                    class="w-full rounded-xl bg-ink-950 py-3 font-semibold text-white transition hover:bg-ink-900 disabled:opacity-50 dark:bg-accent dark:text-ink-950 dark:hover:bg-accent-dim"
                    :disabled="submitLoading"
                    @click="submitLead"
                  >
                    {{ submitLoading ? "Отправка…" : "Получить консультацию" }}
                  </button>
                </div>
              </section>

              <section v-else class="space-y-4 rounded-2xl border border-ink-200 bg-white p-6 shadow-card dark:border-ink-700 dark:bg-ink-900">
                <p class="text-ink-800 dark:text-ink-200">
                  Тип блока «<strong>{{ currentNode.type }}</strong>» пока не поддерживается на публичной странице.
                </p>
              </section>
            </div>
          </Transition>
        </div>

        <div v-if="showFooterNext()" class="mt-10 flex items-center justify-between gap-4">
          <button
            type="button"
            class="rounded-xl border border-ink-200 bg-white px-5 py-2.5 text-sm font-medium text-ink-900 transition hover:bg-ink-50 disabled:opacity-40 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100 dark:hover:bg-ink-800"
            :disabled="navStack.length <= 1"
            @click="goBack"
          >
            Назад
          </button>
          <button
            type="button"
            class="rounded-xl bg-ink-950 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-ink-900 disabled:opacity-40 dark:bg-accent dark:text-ink-950 dark:hover:bg-accent-dim"
            :disabled="!canProceed"
            @click="onNextClick"
          >
            Далее
          </button>
        </div>

        <div v-else-if="currentNode.type === 'single'" class="mt-10 flex justify-start">
          <button
            type="button"
            class="rounded-xl border border-ink-200 bg-white px-5 py-2.5 text-sm font-medium text-ink-900 hover:bg-ink-50 disabled:opacity-40 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100 dark:hover:bg-ink-800"
            :disabled="navStack.length <= 1"
            @click="goBack"
          >
            Назад
          </button>
        </div>

        <div v-else-if="currentNode.type === 'form'" class="mt-6 flex justify-start">
          <button
            type="button"
            class="rounded-xl border border-ink-200 bg-white px-5 py-2.5 text-sm font-medium text-ink-900 hover:bg-ink-50 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100 dark:hover:bg-ink-800"
            :disabled="navStack.length <= 1"
            @click="goBack"
          >
            Назад
          </button>
        </div>
      </template>

      <section v-else-if="successDone" class="space-y-8 text-center">
        <div class="mx-auto max-w-md rounded-3xl border border-ink-200 bg-white p-8 shadow-lift dark:border-ink-700 dark:bg-ink-900">
          <p class="text-sm font-medium uppercase tracking-wider text-accent-dim">Заявка принята</p>
          <h1 class="mt-2 font-display text-3xl font-semibold text-ink-950 dark:text-ink-50">Спасибо!</h1>
          <p class="mt-2 text-ink-800/80 dark:text-ink-300">Номер заявки</p>
          <p class="mt-1 font-mono text-2xl font-bold text-ink-950 dark:text-ink-50">{{ requestNumber }}</p>
          <div class="mt-6 flex justify-center">
            <img v-if="qrDataUrl" :src="qrDataUrl" alt="QR" class="rounded-xl border border-ink-100 dark:border-ink-600" />
          </div>
          <p class="mt-4 text-sm text-ink-800/70 dark:text-ink-400">
            Отсканируйте QR или откройте статус по ссылке — мы сохранили её в этом браузере.
          </p>
          <RouterLink
            v-if="lastSubmittedLead"
            :to="`/lead/${lastSubmittedLead.id}`"
            class="mt-4 inline-flex rounded-xl bg-ink-950 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink-900 dark:bg-accent dark:text-ink-950 dark:hover:bg-accent-dim"
          >
            Открыть статус заявки
          </RouterLink>
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
