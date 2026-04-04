<script setup lang="ts">
import { inject } from "vue";
import { Panel, useVueFlow } from "@vue-flow/core";
import type { QuizBlockType } from "@/types/quiz-schema";
import { QUIZ_BLOCK_TYPES } from "@/types/quiz-schema";
import { quizFlowActionsKey } from "./injection";

const { fitView, zoomIn, zoomOut } = useVueFlow();
const actions = inject(quizFlowActionsKey);

function add(t: QuizBlockType): void {
  actions?.addBlock(t);
}

function remove(): void {
  actions?.deleteSelection();
}
</script>

<template>
  <Panel position="top-left" class="m-2 flex flex-wrap gap-2 rounded-xl border border-ink-500/80 bg-ink-900/95 p-2.5 shadow-2xl backdrop-blur-md">
    <div class="flex flex-wrap gap-1 border-r border-ink-600 pr-2.5">
      <span class="w-full text-[9px] font-semibold uppercase tracking-wider text-ink-500">Добавить блок</span>
      <button
        v-for="bt in QUIZ_BLOCK_TYPES"
        :key="bt.value"
        type="button"
        class="rounded-lg bg-ink-800 px-2 py-1.5 text-[11px] font-medium text-ink-100 transition hover:bg-accent hover:text-ink-950"
        @click="add(bt.value)"
      >
        {{ bt.label }}
      </button>
    </div>
    <div class="flex flex-wrap items-center gap-1 border-r border-ink-600 pr-2.5">
      <span class="w-full text-[9px] font-semibold uppercase tracking-wider text-ink-500">Удалить</span>
      <button
        type="button"
        class="rounded-lg border border-red-900/60 bg-red-950/40 px-2.5 py-1.5 text-[11px] font-medium text-red-200 hover:bg-red-900/50"
        title="Удалить выбранные ноды (или текущую в панели справа)"
        @click="remove"
      >
        Выбранные
      </button>
    </div>
    <div class="flex flex-wrap gap-1">
      <span class="w-full text-[9px] font-semibold uppercase tracking-wider text-ink-500">Вид</span>
      <button
        type="button"
        class="rounded-lg border border-ink-600 px-2.5 py-1.5 text-[11px] text-ink-200 hover:bg-ink-800"
        title="Подогнать схему в кадр"
        @click="fitView({ padding: 0.25, duration: 280 })"
      >
        В кадр
      </button>
      <button type="button" class="rounded-lg border border-ink-600 px-2.5 py-1.5 text-[11px] text-ink-200 hover:bg-ink-800" @click="zoomIn()">
        +
      </button>
      <button type="button" class="rounded-lg border border-ink-600 px-2.5 py-1.5 text-[11px] text-ink-200 hover:bg-ink-800" @click="zoomOut()">
        −
      </button>
    </div>
  </Panel>
</template>
