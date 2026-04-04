<script setup lang="ts">
import { computed, markRaw, nextTick, onMounted, onUnmounted, provide, ref, watch } from "vue";
import { useTheme } from "@/composables/useTheme";
import {
  VueFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
  type NodeDragEvent,
  type NodeMouseEvent,
} from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import type { QuizBlockType, QuizNode, QuizSchema } from "@/types/quiz-schema";
import { QUIZ_BLOCK_TYPES } from "@/types/quiz-schema";
import { defaultFlowPosition, schemaToFlowElements, flowToSchema } from "./schemaFlow";
import QuizBlockNode from "./nodes/QuizBlockNode.vue";
import QuizFlowToolbar from "./QuizFlowToolbar.vue";
import {
  quizCanvasOptionFocusKey,
  quizFlowActionsKey,
  quizIdTitlesKey,
  QUIZ_PALETTE_DRAG_MIME,
  quizBlockTypeFromDragData,
  type CanvasOptionFocusRequest,
} from "./injection";

const props = defineProps<{
  schema: QuizSchema | null;
}>();

const { isDark } = useTheme();

/**
 * У draggable-нод Vue Flow вешает класс nopan: жест pan/zoom на холсте для touchstart с цели «нода»
 * отфильтровывается. На телефоне фона между карточками часто нет — вид «застывает».
 * Для (pointer: coarse) отключаем drag нод: pan работает по всей области, позиции править с ПК.
 */
const nodeDragOnCanvas = ref(true);
/** Сенсор без точного указателя — показываем кнопки отмены/повтора (нет Ctrl+Z/Y) */
const isCoarsePointer = ref(false);

function syncNodeDragForPointer(): void {
  try {
    const coarse = window.matchMedia("(pointer: coarse)").matches;
    isCoarsePointer.value = coarse;
    nodeDragOnCanvas.value = !coarse;
  } catch {
    isCoarsePointer.value = false;
    nodeDragOnCanvas.value = true;
  }
}

/** Локальный тип вместо FlowNode<{ quiz: QuizNode }> — иначе TS2589 excessively deep */
type QuizFlowNode = {
  id: string;
  type?: string;
  position: { x: number; y: number };
  data: { quiz: QuizNode };
  selected?: boolean;
};

/** Обход TS2589 (excessively deep) при обходе Edge[] из Vue Flow */
type SlimEdge = { id: string; source: string; target: string; sourceHandle?: string | null };

const nodes = ref<QuizFlowNode[]>([]);
const edges = ref<Edge[]>([]);
const selectedId = ref<string | null>(null);
const canvasOptionFocus = ref<CanvasOptionFocusRequest>(null);
provide(quizCanvasOptionFocusKey, canvasOptionFocus);

const MAX_UNDO = 60;
const undoStack = ref<QuizSchema[]>([]);
const redoStack = ref<QuizSchema[]>([]);
/** Не писать в стек при загрузке схемы / undo / redo */
const historySuspended = ref(false);
/** Пропуск автоснимка при remove из Vue Flow после наших же мутаций nodes/edges */
const skipGraphRemoveHistory = ref(0);
/** removeNodes в Vue Flow: сначала edgesChange(remove), потом nodesChange(remove) — один шаг истории */
let skipDuplicateNodeRemoveHistory = false;

/** Координаты последнего клика по canvas (flow space) — новый блок ставим сюда */
const lastFlowTapPosition = ref<{ x: number; y: number } | null>(null);
/** Публичные методы VueFlow (screenToFlowCoordinate) — ref на корень графа */
const vueFlowRef = ref<{ screenToFlowCoordinate?: (p: { x: number; y: number }) => { x: number; y: number } } | null>(
  null,
);
/** Область схемы (под VueFlow) — центр экрана → координаты flow для нового блока */
const flowAreaElRef = ref<HTMLElement | null>(null);

function snapFlowCoord(v: number): number {
  const g = 16;
  return Math.round(v / g) * g;
}

function rememberFlowTap(clientX: number, clientY: number): void {
  const vf = vueFlowRef.value;
  if (!vf?.screenToFlowCoordinate) return;
  const flow = vf.screenToFlowCoordinate({ x: clientX, y: clientY });
  lastFlowTapPosition.value = { x: Math.round(flow.x), y: Math.round(flow.y) };
}

function clientXYFromPointerLike(ev: Event): { x: number; y: number } | null {
  if ("clientX" in ev && typeof (ev as MouseEvent).clientX === "number") {
    const m = ev as MouseEvent;
    return { x: m.clientX, y: m.clientY };
  }
  const te = ev as TouchEvent;
  const t = te.touches?.[0] ?? te.changedTouches?.[0];
  if (t) return { x: t.clientX, y: t.clientY };
  return null;
}

function positionForNewBlock(): { x: number; y: number } {
  const p = lastFlowTapPosition.value;
  if (p) return { x: snapFlowCoord(p.x), y: snapFlowCoord(p.y) };

  const vf = vueFlowRef.value;
  const wrap = flowAreaElRef.value;
  if (vf?.screenToFlowCoordinate && wrap) {
    const r = wrap.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      const flow = vf.screenToFlowCoordinate({
        x: r.left + r.width / 2,
        y: r.top + r.height / 2,
      });
      return { x: snapFlowCoord(flow.x), y: snapFlowCoord(flow.y) };
    }
  }

  return defaultFlowPosition(Math.min(nodes.value.length, 7));
}

function captureSchemaSnapshot(): QuizSchema {
  return JSON.parse(
    JSON.stringify(flowToSchema(nodes.value as never, edges.value as never)),
  ) as QuizSchema;
}

function pushUndoSnapshot(): void {
  if (historySuspended.value) return;
  const snap = captureSchemaSnapshot();
  const last = undoStack.value[undoStack.value.length - 1];
  if (last && JSON.stringify(last) === JSON.stringify(snap)) return;
  undoStack.value.push(snap);
  if (undoStack.value.length > MAX_UNDO) undoStack.value.shift();
  redoStack.value = [];
}

let editBurstTimer: ReturnType<typeof setTimeout> | null = null;
let editBurstHasUndo = false;
function beginEditBurst(): void {
  if (historySuspended.value) return;
  if (!editBurstHasUndo) {
    pushUndoSnapshot();
    editBurstHasUndo = true;
  }
  if (editBurstTimer) clearTimeout(editBurstTimer);
  editBurstTimer = setTimeout(() => {
    editBurstHasUndo = false;
    editBurstTimer = null;
  }, 480);
}

const nodeTypes = { quizBlock: markRaw(QuizBlockNode) };

const canUndo = computed(() => !historySuspended.value && undoStack.value.length > 0);
const canRedo = computed(() => !historySuspended.value && redoStack.value.length > 0);

const idToTitles = computed(() => {
  const m: Record<string, string> = {};
  for (const n of nodes.value) {
    const q = (n.data as { quiz: QuizNode } | undefined)?.quiz;
    m[n.id] = (q?.title?.trim() || q?.id || n.id) as string;
  }
  return m;
});

provide(quizIdTitlesKey, idToTitles);

function targetLabel(targetId: string): string {
  return idToTitles.value[targetId] || targetId;
}

/** Меняется только при смене id/заголовка блока — не при перетаскивании (иначе лишние проходы) */
const titlesSignature = computed(() =>
  nodes.value
    .map((n) => {
      const q = (n.data as { quiz: QuizNode })?.quiz;
      const t = (q?.title?.trim() || q?.id || n.id) as string;
      return `${n.id}\0${t}`;
    })
    .sort()
    .join("\n"),
);

/** Подпись на стрелке = заголовок целевого блока; обновляем при смене типа/названия в инспекторе */
function refreshEdgeLabels(): void {
  const titles = idToTitles.value;
  const cur = edges.value as unknown as Array<Edge & { label?: string }>;
  edges.value = cur.map((e) => ({
    ...e,
    label: titles[e.target] ?? e.target,
  })) as unknown as Edge[];
}

watch(titlesSignature, () => {
  refreshEdgeLabels();
});

const defaultEdgeOpts = computed(() => ({
  type: "smoothstep" as const,
  style: { stroke: "#c9a962", strokeWidth: 2 },
  labelStyle: isDark.value
    ? { fill: "#e8e4dc", fontSize: 11, fontWeight: 500 as const }
    : { fill: "#1a1b20", fontSize: 11, fontWeight: 500 as const },
  labelBgStyle: isDark.value
    ? { fill: "#1f222d", fillOpacity: 0.92 }
    : { fill: "#ffffff", fillOpacity: 0.95 },
  labelBgPadding: [4, 6] as [number, number],
}));

/** Подписи на связях при переключении светлой/тёмной темы */
watch(isDark, () => {
  const lo = defaultEdgeOpts.value;
  edges.value = edges.value.map((e) => ({
    ...e,
    labelStyle: { ...lo.labelStyle },
    labelBgStyle: { ...lo.labelBgStyle },
    style: { ...lo.style, ...(e.style && typeof e.style === "object" ? e.style : {}) },
  })) as Edge[];
});

function defaultQuiz(type: QuizBlockType, id: string): QuizNode {
  switch (type) {
    case "single":
      return {
        id,
        type: "single",
        title: "Новый вопрос",
        options: [
          { id: "a", label: "Вариант A", nextStep: "" },
          { id: "b", label: "Вариант B", nextStep: "" },
        ],
      };
    case "multi":
      return {
        id,
        type: "multi",
        title: "Выберите зоны",
        options: [
          { id: "o1", label: "Пункт 1" },
          { id: "o2", label: "Пункт 2" },
        ],
        nextStep: "",
      };
    case "slider":
      return { id, type: "slider", title: "Площадь", min: 20, max: 300, step: 5, default: 60, nextStep: "" };
    case "form":
      return { id, type: "form", title: "Контакты", nextStep: "" };
    case "ai_summary":
      return { id, type: "ai_summary", title: "Резюме", nextStep: "" };
    default:
      return { id, type: "form", title: "Блок", nextStep: "" };
  }
}

function addBlock(type: QuizBlockType, atFlowPosition?: { x: number; y: number }): string {
  pushUndoSnapshot();
  const id = `step_${Date.now()}`;
  const quiz = defaultQuiz(type, id);
  const pos = atFlowPosition
    ? { x: snapFlowCoord(atFlowPosition.x), y: snapFlowCoord(atFlowPosition.y) }
    : positionForNewBlock();
  const newNode: QuizFlowNode = {
    id,
    type: "quizBlock",
    position: pos,
    data: { quiz },
  };
  nodes.value = [...nodes.value, newNode];
  return id;
}

function onPaletteStripDragStart(e: DragEvent, t: QuizBlockType): void {
  const dt = e.dataTransfer;
  if (!dt) return;
  dt.setData(QUIZ_PALETTE_DRAG_MIME, t);
  dt.setData("text/plain", t);
  dt.effectAllowed = "copy";
}

function isPaletteDragEvent(dt: DataTransfer): boolean {
  return dt.types.includes(QUIZ_PALETTE_DRAG_MIME) || dt.types.includes("text/plain");
}

function onPaletteDragOver(e: DragEvent): void {
  const dt = e.dataTransfer;
  if (!dt || !isPaletteDragEvent(dt)) return;
  e.preventDefault();
  dt.dropEffect = "copy";
}

function onPaletteDrop(e: DragEvent): void {
  const dt = e.dataTransfer;
  if (!dt) return;
  const type = quizBlockTypeFromDragData(dt);
  if (!type) return;
  e.preventDefault();
  const vf = vueFlowRef.value;
  let flowPos: { x: number; y: number };
  if (vf?.screenToFlowCoordinate) {
    flowPos = vf.screenToFlowCoordinate({ x: e.clientX, y: e.clientY });
  } else {
    flowPos = positionForNewBlock();
  }
  const id = addBlock(type, flowPos);
  selectedId.value = id;
}

function deleteSelection(): void {
  const sel = new Set(nodes.value.filter((n) => n.selected).map((n) => n.id));
  if (sel.size === 0 && selectedId.value) sel.add(selectedId.value);
  if (sel.size === 0) return;
  pushUndoSnapshot();
  skipGraphRemoveHistory.value += 1;
  nodes.value = nodes.value.filter((n) => !sel.has(n.id));
  const edgePairs = edges.value as unknown as { source: string; target: string }[];
  edges.value = edgePairs.filter((e) => !sel.has(e.source) && !sel.has(e.target)) as unknown as Edge[];
  selectedId.value = null;
  nextTick(() => {
    skipGraphRemoveHistory.value = Math.max(0, skipGraphRemoveHistory.value - 1);
  });
}

function addCanvasOption(nodeId: string): void {
  pushUndoSnapshot();
  const newId = `opt_${Date.now()}`;
  nodes.value = nodes.value.map((n) => {
    if (n.id !== nodeId) return n;
    const q = { ...(n.data as { quiz: QuizNode }).quiz };
    if (q.type !== "single" && q.type !== "multi") return n;
    const prev = q.options ?? [];
    const nextOpt =
      q.type === "single"
        ? { id: newId, label: "", nextStep: "" }
        : { id: newId, label: "" };
    q.options = [...prev, nextOpt];
    return { ...n, data: { quiz: q } };
  });
  canvasOptionFocus.value = { nodeId, optionId: newId };
}

function setCanvasOptionLabel(nodeId: string, optionId: string, label: string): void {
  beginEditBurst();
  nodes.value = nodes.value.map((n) => {
    if (n.id !== nodeId) return n;
    const q = { ...(n.data as { quiz: QuizNode }).quiz };
    if (!q.options?.length) return n;
    q.options = q.options.map((o) => (o.id === optionId ? { ...o, label } : o));
    return { ...n, data: { quiz: q } };
  });
}

provide(quizFlowActionsKey, { addBlock, deleteSelection, addCanvasOption, setCanvasOptionLabel });

function hydrateEditorFromSchema(s: QuizSchema | null): void {
  if (!s?.nodes?.length) {
    nodes.value = [];
    edges.value = [];
    selectedId.value = null;
    return;
  }
  const { nodes: n, edges: e } = schemaToFlowElements(s);
  const lo = defaultEdgeOpts.value;
  const withEdgeDefaults = e.map((edge) => ({
    ...lo,
    ...edge,
    type: "smoothstep" as const,
    labelStyle: { ...lo.labelStyle },
    labelBgStyle: { ...lo.labelBgStyle },
  }));
  nodes.value = n as QuizFlowNode[];
  edges.value = withEdgeDefaults;
}

watch(
  () => props.schema,
  (s) => {
    historySuspended.value = true;
    try {
      hydrateEditorFromSchema(s);
      refreshEdgeLabels();
      lastFlowTapPosition.value = null;
      undoStack.value = [];
      redoStack.value = [];
    } finally {
      historySuspended.value = false;
    }
  },
  { immediate: true },
);

/** Рёбра — источник правды для «следующий шаг»; пишем в data.quiz, чтобы инспектор и карточка совпадали с линией */
function syncNextStepsFromEdges(): void {
  const edgeList = edges.value as unknown as SlimEdge[];
  nodes.value = nodes.value.map((n) => {
    const raw = (n.data as { quiz: QuizNode }).quiz;
    const q: QuizNode = { ...raw };
    if (q.type === "single" && q.options?.length) {
      const main = edgeList.find(
        (e) => e.source === n.id && !String(e.sourceHandle ?? "").startsWith("opt-"),
      );
      q.options = q.options.map((opt) => {
        const spec = edgeList.find((e) => e.source === n.id && e.sourceHandle === `opt-${opt.id}`);
        const t = spec?.target ?? main?.target;
        return { ...opt, nextStep: t || undefined };
      });
    } else {
      const main = edgeList.find(
        (e) => e.source === n.id && !String(e.sourceHandle ?? "").startsWith("opt-"),
      );
      q.nextStep = main?.target || undefined;
    }
    return { ...n, data: { quiz: q } };
  });
}

/** Только топология рёбер — без deep watch (Vue Flow постоянно мутирует edge-объекты → был бы бесконечный цикл с sync). */
const edgesTopologyKey = computed(() => {
  const list = edges.value as unknown as SlimEdge[];
  return list
    .map((e) => `${e.id}\0${e.source}\0${e.target}\0${String(e.sourceHandle ?? "")}`)
    .sort()
    .join("\n");
});

watch(edgesTopologyKey, () => {
  syncNextStepsFromEdges();
});

function onConnect(p: Connection): void {
  if (!p.source || !p.target) return;
  pushUndoSnapshot();
  const list = edges.value as unknown as SlimEdge[];
  const filtered = list.filter(
    (e) => !((e.source === p.source && (e.sourceHandle ?? "") === (p.sourceHandle ?? ""))),
  );
  const id = `e-${p.source}-${p.sourceHandle || "d"}-${p.target}-${Date.now()}`;
  const next = [
    ...filtered,
    {
      id,
      source: p.source,
      target: p.target,
      sourceHandle: p.sourceHandle || undefined,
      ...defaultEdgeOpts.value,
      label: targetLabel(p.target),
    },
  ];
  edges.value = next as unknown as Edge[];
}

function onNodeDragStop(ev: NodeDragEvent): void {
  const { node } = ev;
  const x = Math.round(node.position.x);
  const y = Math.round(node.position.y);
  const cur = nodes.value.find((n) => n.id === node.id);
  const ox = cur?.position.x ?? x;
  const oy = cur?.position.y ?? y;
  if (ox === x && oy === y) return;
  pushUndoSnapshot();
  nodes.value = nodes.value.map((n) => (n.id === node.id ? { ...n, position: { x, y } } : n));
}

function onNodeClick(e: NodeMouseEvent): void {
  const ev = e.event;
  selectedId.value = e.node.id;
  if (ev) {
    const xy = clientXYFromPointerLike(ev);
    if (xy) rememberFlowTap(xy.x, xy.y);
  }
}

function onPaneClick(ev: MouseEvent): void {
  selectedId.value = null;
  rememberFlowTap(ev.clientX, ev.clientY);
}

const selectedQuiz = computed(() => {
  const n = nodes.value.find((x) => x.id === selectedId.value);
  if (!n?.data || typeof n.data !== "object" || !("quiz" in n.data)) return null;
  return (n.data as { quiz: QuizNode }).quiz;
});

const targetOptions = computed(() =>
  nodes.value
    .filter((n) => n.id !== selectedId.value)
    .map((n) => {
      const q = (n.data as { quiz: QuizNode }).quiz;
      return { id: n.id, title: q.title?.trim() || n.id };
    }),
);

function patchQuiz(mut: (q: QuizNode) => void): void {
  const id = selectedId.value;
  if (!id) return;
  beginEditBurst();
  nodes.value = nodes.value.map((x) => {
    if (x.id !== id) return x;
    const q = { ...(x.data as { quiz: QuizNode }).quiz };
    mut(q);
    return { ...x, data: { quiz: q } };
  });
}

function setTitle(v: string): void {
  patchQuiz((q) => {
    q.title = v;
  });
}

function changeType(next: QuizBlockType): void {
  const id = selectedId.value;
  if (!id) return;
  pushUndoSnapshot();
  const fresh = defaultQuiz(next, id);
  nodes.value = nodes.value.map((x) => (x.id === id ? { ...x, data: { quiz: fresh } } : x));
}

function addOption(): void {
  patchQuiz((q) => {
    if (q.type !== "single" && q.type !== "multi") return;
    if (!q.options) q.options = [];
    const k = q.options.length + 1;
    q.options.push({ id: `opt_${Date.now()}`, label: `Вариант ${k}`, nextStep: "" });
  });
}

function removeOption(idx: number): void {
  patchQuiz((q) => {
    if (!q.options) return;
    q.options.splice(idx, 1);
  });
}

function setOptionLabel(idx: number, v: string): void {
  patchQuiz((q) => {
    if (!q.options?.[idx]) return;
    q.options[idx].label = v;
  });
}

function setOptionNext(idx: number, v: string): void {
  patchQuiz((q) => {
    if (!q.options?.[idx]) return;
    q.options[idx].nextStep = v || undefined;
  });
}

function setNextStep(v: string): void {
  patchQuiz((q) => {
    q.nextStep = v || undefined;
  });
}

function setSliderMin(v: number): void {
  patchQuiz((q) => {
    if (q.type === "slider") q.min = v;
  });
}
function setSliderMax(v: number): void {
  patchQuiz((q) => {
    if (q.type === "slider") q.max = v;
  });
}
function setSliderStep(v: number): void {
  patchQuiz((q) => {
    if (q.type === "slider") q.step = v;
  });
}
function setSliderDefault(v: number): void {
  patchQuiz((q) => {
    if (q.type === "slider") q.default = v;
  });
}

function getSchema(): QuizSchema {
  // Vue Flow Node/Edge generics → TS2589 при прямой передаче в flowToSchema
  return flowToSchema(nodes.value as never, edges.value as never);
}

function deleteCurrentBlock(): void {
  if (!selectedId.value) return;
  const id = selectedId.value;
  pushUndoSnapshot();
  skipGraphRemoveHistory.value += 1;
  nodes.value = nodes.value.filter((n) => n.id !== id);
  const pairs = edges.value as unknown as { source: string; target: string }[];
  edges.value = pairs.filter((e) => e.source !== id && e.target !== id) as unknown as Edge[];
  selectedId.value = null;
  nextTick(() => {
    skipGraphRemoveHistory.value = Math.max(0, skipGraphRemoveHistory.value - 1);
  });
}

function restoreEditorState(s: QuizSchema | null): void {
  historySuspended.value = true;
  try {
    hydrateEditorFromSchema(s);
    refreshEdgeLabels();
  } finally {
    historySuspended.value = false;
  }
  nextTick(() => syncNextStepsFromEdges());
}

function undo(): void {
  if (historySuspended.value || undoStack.value.length === 0) return;
  redoStack.value.push(captureSchemaSnapshot());
  const prev = undoStack.value.pop()!;
  restoreEditorState(prev?.nodes?.length ? prev : null);
}

function redo(): void {
  if (historySuspended.value || redoStack.value.length === 0) return;
  undoStack.value.push(captureSchemaSnapshot());
  const nxt = redoStack.value.pop()!;
  restoreEditorState(nxt?.nodes?.length ? nxt : null);
}

function onFlowNodesChange(changes: NodeChange[]): void {
  if (historySuspended.value || skipGraphRemoveHistory.value > 0) return;
  if (!changes.some((c) => c.type === "remove")) return;
  if (skipDuplicateNodeRemoveHistory) return;
  pushUndoSnapshot();
}

function onFlowEdgesChange(changes: EdgeChange[]): void {
  if (historySuspended.value || skipGraphRemoveHistory.value > 0) return;
  if (!changes.some((c) => c.type === "remove")) return;
  pushUndoSnapshot();
  skipDuplicateNodeRemoveHistory = true;
  queueMicrotask(() => {
    skipDuplicateNodeRemoveHistory = false;
  });
}

function onUndoRedoKeydown(e: KeyboardEvent): void {
  if (e.repeat) return;
  const t = e.target as Node | null;
  if (
    t &&
    t instanceof Element &&
    t.closest("input, textarea, select, [contenteditable]")
  ) {
    return;
  }
  const mod = e.ctrlKey || e.metaKey;
  if (!mod) return;
  const code = e.code;
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const isUndo =
    (code === "KeyZ" || key === "z") && !e.shiftKey;
  const isRedo =
    code === "KeyY" ||
    key === "y" ||
    ((code === "KeyZ" || key === "z") && e.shiftKey);
  if (isUndo) {
    e.preventDefault();
    e.stopPropagation();
    undo();
  } else if (isRedo) {
    e.preventDefault();
    e.stopPropagation();
    redo();
  }
}

let coarsePointerMq: MediaQueryList | null = null;
const onCoarsePointerChange = () => syncNodeDragForPointer();

onMounted(() => {
  syncNodeDragForPointer();
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    coarsePointerMq = window.matchMedia("(pointer: coarse)");
    coarsePointerMq.addEventListener("change", onCoarsePointerChange);
  }
  document.addEventListener("keydown", onUndoRedoKeydown, true);
});
onUnmounted(() => {
  coarsePointerMq?.removeEventListener("change", onCoarsePointerChange);
  document.removeEventListener("keydown", onUndoRedoKeydown, true);
});

defineExpose({ getSchema });
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-[1fr_308px]">
    <div class="flex min-w-0 flex-col gap-2">
      <div
        class="flex flex-wrap items-end gap-2 rounded-xl border border-ink-200 bg-white/95 p-2.5 shadow-md dark:border-ink-600/80 dark:bg-ink-900/95"
      >
        <div class="flex min-w-0 flex-1 flex-wrap gap-1.5">
          <span
            class="w-full text-[9px] font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-500"
          >
            Добавить блок
          </span>
          <button
            v-for="bt in QUIZ_BLOCK_TYPES"
            :key="bt.value"
            type="button"
            draggable="true"
            class="cursor-grab touch-none rounded-lg bg-ink-100 px-2.5 py-1.5 text-[11px] font-medium text-ink-900 transition hover:bg-accent hover:text-ink-950 active:cursor-grabbing dark:bg-ink-800 dark:text-ink-100 dark:hover:bg-accent dark:hover:text-ink-950"
            @click="addBlock(bt.value)"
            @dragstart="onPaletteStripDragStart($event, bt.value)"
          >
            {{ bt.label }}
          </button>
        </div>
        <p class="max-w-[220px] text-[10px] leading-snug text-ink-500 dark:text-ink-500 max-sm:hidden">
          Перетащите тип блока на схему ниже или нажмите для авто-позиции.
        </p>
        <div
          v-if="isCoarsePointer"
          class="flex w-full flex-wrap items-center gap-2 border-t border-ink-200 pt-2.5 dark:border-ink-600"
        >
          <span
            class="w-full text-[9px] font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-500"
          >
            История (как Ctrl+Z / Ctrl+Y на ПК)
          </span>
          <button
            type="button"
            class="min-h-10 min-w-0 flex-1 rounded-lg border border-ink-200 bg-white px-3 py-2 text-xs font-medium text-ink-900 active:bg-ink-100 disabled:pointer-events-none disabled:opacity-40 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100 dark:active:bg-ink-800"
            :disabled="!canUndo"
            @click="undo()"
          >
            Отменить
          </button>
          <button
            type="button"
            class="min-h-10 min-w-0 flex-1 rounded-lg border border-ink-200 bg-white px-3 py-2 text-xs font-medium text-ink-900 active:bg-ink-100 disabled:pointer-events-none disabled:opacity-40 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100 dark:active:bg-ink-800"
            :disabled="!canRedo"
            @click="redo()"
          >
            Вернуть
          </button>
        </div>
      </div>
      <div
        ref="flowAreaElRef"
        class="vue-flow-wrap relative isolate h-[min(74vh,760px)] min-h-[360px] overflow-hidden overscroll-contain rounded-2xl border border-ink-300 bg-ink-100 shadow-inner dark:border-ink-500/60 dark:bg-[#0c0e14] sm:min-h-[460px]"
        @dragover.capture="onPaletteDragOver"
        @drop.capture="onPaletteDrop"
      >
      <VueFlow
        ref="vueFlowRef"
        v-model:nodes="nodes"
        v-model:edges="edges"
        :node-types="nodeTypes"
        :nodes-draggable="nodeDragOnCanvas"
        :default-viewport="{ zoom: 0.88, x: 20, y: 12 }"
        :default-edge-options="defaultEdgeOpts"
        :min-zoom="0.15"
        :max-zoom="1.6"
        :snap-to-grid="true"
        :snap-grid="[16, 16]"
        :delete-key-code="['Backspace', 'Delete']"
        :pan-on-drag="true"
        :zoom-on-pinch="true"
        :zoom-on-scroll="true"
        class="quiz-vue-flow"
        @connect="onConnect"
        @node-drag-stop="onNodeDragStop"
        @node-click="onNodeClick"
        @pane-click="onPaneClick"
        @nodesChange="onFlowNodesChange"
        @edgesChange="onFlowEdgesChange"
      >
        <Background :gap="22" pattern-color="#c4c5cd" :size="1.2" class="dark:hidden" />
        <Background :gap="22" pattern-color="#2a2e3d" :size="1.2" class="hidden dark:block" />
        <Controls :show-interactive="false" class="controls-dark !m-2.5" />
        <QuizFlowToolbar />
      </VueFlow>
      <p
        class="pointer-events-none absolute bottom-3 left-4 right-4 text-center text-[10px] leading-relaxed text-ink-600 dark:text-ink-500"
      >
        <span class="sm:hidden">
          Пальцем по схеме — сдвиг и масштаб (щипок). Перетаскивать сами блоки на телефоне нельзя — только с ПК/мыши.
        </span>
        Перетаскивайте карточки — координаты сохраняются при «Сохранить схему» · тяните линию от
        <span class="font-medium text-accent-dim dark:text-accent-dim">янтарной точки</span>
        к следующему блоку ·
        <span class="text-ink-700 dark:text-ink-400">Backspace / Delete</span>
        или кнопка «Выбранные»
        · <span class="text-ink-700 dark:text-ink-400">Ctrl+Z</span> отмена ·
        <span class="text-ink-700 dark:text-ink-400">Ctrl+Y</span> /
        <span class="text-ink-700 dark:text-ink-400">Ctrl+Shift+Z</span> повтор
        · с палитры сверху перетащите тип блока на схему
      </p>
      </div>
    </div>

    <aside
      class="space-y-4 rounded-2xl border border-ink-200 bg-gradient-to-b from-white to-ink-50 p-4 shadow-xl dark:border-ink-600/80 dark:from-ink-900/90 dark:to-ink-950/90"
    >
      <h3 class="font-display text-sm font-semibold tracking-tight text-ink-950 dark:text-white">Свойства блока</h3>
      <p v-if="!selectedQuiz" class="text-xs leading-relaxed text-ink-600 dark:text-ink-500">
        Выберите карточку на схеме. Удаление: клавиши Backspace/Delete, кнопка на canvas или ниже.
      </p>
      <template v-else>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-800 hover:bg-red-100 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-200 dark:hover:bg-red-900/40"
            @click="deleteCurrentBlock"
          >
            Удалить этот блок
          </button>
        </div>
        <label class="block text-[11px] text-ink-600 dark:text-ink-400">
          Внутренний ID
          <input
            :value="selectedQuiz.id"
            disabled
            class="mt-1 w-full rounded-lg border border-ink-200 bg-ink-50 px-2 py-1.5 font-mono text-[11px] text-ink-600 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-500"
          />
        </label>
        <label class="block text-[11px] text-ink-600 dark:text-ink-400">
          Заголовок на карточке
          <input
            :value="selectedQuiz.title ?? ''"
            class="mt-1 w-full rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm text-ink-950 placeholder:text-ink-500 focus:border-accent focus:outline-none dark:border-ink-600 dark:bg-ink-950 dark:text-white dark:placeholder:text-ink-600"
            placeholder="Например: Зоны"
            @input="setTitle(($event.target as HTMLInputElement).value)"
          />
        </label>
        <label class="block text-[11px] text-ink-600 dark:text-ink-400">
          Тип
          <select
            :value="selectedQuiz.type"
            class="mt-1 w-full rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm text-ink-950 focus:border-accent focus:outline-none dark:border-ink-600 dark:bg-ink-950 dark:text-white"
            @change="changeType(($event.target as HTMLSelectElement).value as QuizBlockType)"
          >
            <option value="single">Одиночный выбор</option>
            <option value="multi">Множественный</option>
            <option value="slider">Ползунок</option>
            <option value="form">Форма</option>
            <option value="ai_summary">ИИ-резюме</option>
          </select>
        </label>

        <template v-if="selectedQuiz.type === 'slider'">
          <div class="grid grid-cols-2 gap-2">
            <label class="text-[11px] text-ink-600 dark:text-ink-400"
              >Min
              <input
                :value="selectedQuiz.min ?? 0"
                type="number"
                class="mt-1 w-full rounded-lg border border-ink-200 bg-white px-2 py-1 text-xs text-ink-950 dark:border-ink-600 dark:bg-ink-950 dark:text-white"
                @change="setSliderMin(Number(($event.target as HTMLInputElement).value))"
              />
            </label>
            <label class="text-[11px] text-ink-600 dark:text-ink-400"
              >Max
              <input
                :value="selectedQuiz.max ?? 100"
                type="number"
                class="mt-1 w-full rounded-lg border border-ink-200 bg-white px-2 py-1 text-xs text-ink-950 dark:border-ink-600 dark:bg-ink-950 dark:text-white"
                @change="setSliderMax(Number(($event.target as HTMLInputElement).value))"
              />
            </label>
            <label class="text-[11px] text-ink-600 dark:text-ink-400"
              >Шаг
              <input
                :value="selectedQuiz.step ?? 1"
                type="number"
                class="mt-1 w-full rounded-lg border border-ink-200 bg-white px-2 py-1 text-xs text-ink-950 dark:border-ink-600 dark:bg-ink-950 dark:text-white"
                @change="setSliderStep(Number(($event.target as HTMLInputElement).value))"
              />
            </label>
            <label class="text-[11px] text-ink-600 dark:text-ink-400"
              >По умолчанию
              <input
                :value="selectedQuiz.default ?? 0"
                type="number"
                class="mt-1 w-full rounded-lg border border-ink-200 bg-white px-2 py-1 text-xs text-ink-950 dark:border-ink-600 dark:bg-ink-950 dark:text-white"
                @change="setSliderDefault(Number(($event.target as HTMLInputElement).value))"
              />
            </label>
          </div>
        </template>

        <template v-if="(selectedQuiz.type === 'single' || selectedQuiz.type === 'multi') && selectedQuiz.options">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-medium text-ink-600 dark:text-ink-400">Варианты</span>
            <button type="button" class="text-[11px] font-medium text-accent hover:underline" @click="addOption">+ вариант</button>
          </div>
          <div class="max-h-52 space-y-2 overflow-y-auto pr-0.5">
            <div
              v-for="(opt, idx) in selectedQuiz.options"
              :key="opt.id"
              class="rounded-xl border border-ink-200 bg-ink-50 p-2.5 dark:border-ink-700 dark:bg-ink-950/70"
            >
              <div class="flex gap-1.5">
                <input
                  :value="opt.label"
                  class="min-w-0 flex-1 rounded-lg border border-ink-200 bg-white px-2 py-1 text-xs text-ink-950 dark:border-ink-600 dark:bg-ink-900 dark:text-white"
                  @input="setOptionLabel(idx, ($event.target as HTMLInputElement).value)"
                />
                <button
                  type="button"
                  class="shrink-0 rounded px-2 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
                  @click="removeOption(idx)"
                >
                  ×
                </button>
              </div>
              <label v-if="selectedQuiz.type === 'single'" class="mt-2 block text-[10px] text-ink-600 dark:text-ink-500">
                Следующий шаг (или соедините линией с карточки)
                <select
                  :value="opt.nextStep ?? ''"
                  class="mt-1 w-full rounded-lg border border-ink-200 bg-white px-2 py-1 text-xs text-ink-950 dark:border-ink-600 dark:bg-ink-900 dark:text-white"
                  @change="setOptionNext(idx, ($event.target as HTMLSelectElement).value)"
                >
                  <option value="">— не выбрано —</option>
                  <option v-for="t in targetOptions" :key="t.id" :value="t.id">{{ t.title }}</option>
                </select>
              </label>
            </div>
          </div>
        </template>

        <label v-if="selectedQuiz.type !== 'single'" class="block text-[11px] text-ink-600 dark:text-ink-400">
          Следующий шаг
          <select
            :value="selectedQuiz.nextStep ?? ''"
            class="mt-1 w-full rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm text-ink-950 dark:border-ink-600 dark:bg-ink-950 dark:text-white"
            @change="setNextStep(($event.target as HTMLSelectElement).value)"
          >
            <option value="">— не выбрано —</option>
            <option v-for="t in targetOptions" :key="t.id" :value="t.id">{{ t.title }}</option>
          </select>
        </label>
      </template>
    </aside>
  </div>
</template>

<style scoped>
/* Явно отдаём жесты зум/пан D3: на мобилке родительский overflow-x и браузерный scroll иначе перехватывают касание. */
.quiz-vue-flow :deep(.vue-flow__viewport),
.quiz-vue-flow :deep(.vue-flow__pane),
.quiz-vue-flow :deep(.vue-flow__renderer) {
  touch-action: none;
}
.quiz-vue-flow :deep(.vue-flow__node input),
.quiz-vue-flow :deep(.vue-flow__node textarea),
.quiz-vue-flow :deep(.vue-flow__node select) {
  touch-action: manipulation;
}
.quiz-vue-flow :deep(.vue-flow__edge-text) {
  font-weight: 500;
}
.quiz-vue-flow :deep(.vue-flow__edge .vue-flow__edge-path) {
  stroke-linecap: round;
}
.controls-dark :deep(button) {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #d5d6db;
  border-radius: 8px;
  color: #1a1b20;
}
.controls-dark :deep(button:hover) {
  background: #ececee;
  color: #0f1014;
}
:global(.dark) .controls-dark :deep(button) {
  background: rgb(30 32 42 / 0.95);
  border: 1px solid rgb(60 64 78);
  color: #c4c8d4;
}
:global(.dark) .controls-dark :deep(button:hover) {
  background: rgb(45 48 60);
  color: #fff;
}
.controls-dark :deep(svg) {
  fill: currentColor;
}
</style>
