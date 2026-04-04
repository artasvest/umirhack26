<script setup lang="ts">
import { computed, inject, nextTick, watch } from "vue";
import { Handle, Position, type NodeProps } from "@vue-flow/core";
import type { QuizNode } from "@/types/quiz-schema";
import { quizCanvasOptionFocusKey, quizFlowActionsKey, quizIdTitlesKey } from "../injection";

/** Полный контракт Vue Flow — иначе тип ноды не совпадает с NodeComponent и граф может не монтироваться */
const props = defineProps<NodeProps<{ quiz: QuizNode }>>();

const actions = inject(quizFlowActionsKey, null);
const focusRef = inject(quizCanvasOptionFocusKey, null);
const titles = inject(quizIdTitlesKey, null);

function titleOf(id: string): string {
  return titles?.value?.[id] ?? id;
}

const q = computed((): QuizNode => {
  const quiz = props.data?.quiz;
  if (quiz) return quiz;
  return { id: props.id, type: "form", title: "Блок", nextStep: "" };
});
const isSingle = computed(() => q.value.type === "single");
const isMulti = computed(() => q.value.type === "multi");
const options = computed(() => q.value.options ?? []);

/**
 * Нельзя хранить DOM в ref и обновлять его из :ref-колбэка — каждый рендер вызывает колбэк,
 * запись в ref → новый рендер → Maximum recursive updates exceeded.
 */
const optInputEls = new Map<string, HTMLInputElement>();

function setOptInputRef(optionId: string, el: unknown): void {
  if (el instanceof HTMLInputElement) {
    optInputEls.set(optionId, el);
  } else {
    optInputEls.delete(optionId);
  }
}

if (focusRef) {
  watch(
    () => focusRef.value,
    async (req) => {
      if (!req || req.nodeId !== props.id) return;
      await nextTick();
      let el = optInputEls.get(req.optionId);
      if (!el) await nextTick();
      el = optInputEls.get(req.optionId);
      el?.focus();
      el?.select();
      focusRef.value = null;
    },
  );
}

function onLabelInput(optionId: string, ev: Event): void {
  const v = (ev.target as HTMLInputElement).value;
  actions?.setCanvasOptionLabel(props.id, optionId, v);
}

function addOptionClick(ev: MouseEvent): void {
  ev.stopPropagation();
  actions?.addCanvasOption(props.id);
}

const handleConnectable = computed(() => props.connectable ?? true);

const typeLabel: Record<string, string> = {
  single: "Один вариант",
  multi: "Несколько",
  slider: "Ползунок",
  form: "Форма",
  ai_summary: "ИИ-резюме",
};

const inputClass =
  "min-w-0 flex-1 rounded border border-transparent bg-transparent px-1 py-0.5 text-[11px] leading-tight text-ink-100 placeholder:text-ink-600 focus:border-ink-500 focus:bg-ink-950/80 focus:outline-none";

const addBtnClass =
  "mt-1 w-full rounded-lg border border-dashed border-ink-600/70 py-1.5 text-[10px] font-medium text-ink-400 transition hover:border-accent/45 hover:bg-ink-800/40 hover:text-accent";
</script>

<template>
  <div
    class="quiz-block-node w-[min(100%,260px)] select-none rounded-2xl border border-ink-500/80 bg-gradient-to-b from-ink-800 to-ink-900 p-0 shadow-xl ring-1 ring-black/20"
  >
    <Handle
      type="target"
      :position="Position.Top"
      :connectable="handleConnectable"
      class="!h-3.5 !w-3.5 !border-2 !border-accent !bg-ink-950 !shadow-md"
    />

    <div class="border-b border-ink-600/80 px-3 py-2">
      <div class="text-[9px] font-bold uppercase tracking-widest text-accent/90">{{ typeLabel[q.type] || q.type }}</div>
      <div class="mt-1 font-display text-[15px] font-semibold leading-snug text-white">
        {{ q.title?.trim() || "Без названия" }}
      </div>
    </div>

    <!-- Одиночный выбор: варианты + ветвление ручками -->
    <div v-if="isSingle && options.length" class="px-1 py-1">
      <div
        v-for="opt in options"
        :key="opt.id"
        class="group relative flex min-h-[32px] items-center gap-2 rounded-lg px-2 py-1.5 pr-4 hover:bg-ink-700/40"
      >
        <span class="size-1.5 shrink-0 rounded-full bg-accent/80" aria-hidden="true" />
        <input
          :ref="(el) => setOptInputRef(opt.id, el)"
          :value="opt.label"
          type="text"
          :class="inputClass"
          placeholder="Текст варианта"
          @pointerdown.stop
          @mousedown.stop
          @input="onLabelInput(opt.id, $event)"
        />
        <span
          v-if="opt.nextStep"
          class="hidden max-w-[64px] shrink-0 truncate text-[9px] text-accent-dim/90 sm:block"
          :title="titleOf(opt.nextStep)"
        >
          → {{ titleOf(opt.nextStep) }}
        </span>
        <Handle
          :id="'opt-' + opt.id"
          type="source"
          :position="Position.Right"
          :connectable="handleConnectable"
          class="quiz-opt-handle !absolute !right-[-10px] top-1/2 z-10 !h-3 !w-3 !-translate-y-1/2 !border-2 !border-ink-700 !bg-accent !shadow-md transition group-hover:!scale-110 group-hover:!border-accent"
        />
      </div>
      <button type="button" :class="addBtnClass" @click="addOptionClick">+ вариант</button>
    </div>

    <div v-else-if="isSingle && !options.length" class="px-2 py-2">
      <button type="button" :class="addBtnClass" @click="addOptionClick">+ вариант</button>
    </div>

    <!-- Множественный: развёрнутый список, без ветвления по пунктам -->
    <div v-else-if="isMulti" class="px-1 py-1">
      <p v-if="!options.length" class="mb-1 px-1 text-[10px] text-ink-500">Отметьте подходящие пункты — добавьте их ниже.</p>
      <div
        v-for="opt in options"
        :key="opt.id"
        class="flex min-h-[32px] items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-ink-700/35"
      >
        <span class="size-1.5 shrink-0 rounded-sm border border-violet-400/90 bg-violet-500/25" aria-hidden="true" />
        <input
          :ref="(el) => setOptInputRef(opt.id, el)"
          :value="opt.label"
          type="text"
          :class="inputClass"
          placeholder="Текст пункта"
          @pointerdown.stop
          @mousedown.stop
          @input="onLabelInput(opt.id, $event)"
        />
      </div>
      <button type="button" :class="addBtnClass" @click="addOptionClick">+ пункт</button>
      <p v-if="q.nextStep" class="mx-1 mt-1 rounded-md border border-ink-700/40 bg-ink-950/40 px-2 py-1 text-[9px] text-ink-500">
        Далее: <span class="font-medium text-accent-dim">{{ titleOf(q.nextStep) }}</span>
      </p>
    </div>

    <div v-else-if="q.type === 'slider'" class="px-3 py-2 text-[10px] text-ink-400">
      Диапазон {{ q.min ?? 0 }}–{{ q.max ?? 100 }} · шаг {{ q.step ?? 1 }}
    </div>
    <div v-else-if="q.nextStep" class="px-3 py-2 text-[10px] text-ink-400">
      Далее: <span class="text-accent-dim">{{ titleOf(q.nextStep) }}</span>
    </div>

    <Handle
      v-if="!isSingle || !options.length"
      id="default"
      type="source"
      :position="Position.Bottom"
      :connectable="handleConnectable"
      class="!h-3.5 !w-3.5 !border-2 !border-accent !bg-ink-950 !shadow-md"
    />
  </div>
</template>

<style scoped>
.quiz-opt-handle {
  position: absolute;
}
</style>
