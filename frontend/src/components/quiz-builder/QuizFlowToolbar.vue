<script setup lang="ts">
import { inject } from "vue";
import { Panel, useVueFlow } from "@vue-flow/core";
import { quizFlowActionsKey } from "./injection";

const { fitView, zoomIn, zoomOut } = useVueFlow();
const actions = inject(quizFlowActionsKey);

function remove(): void {
  actions?.deleteSelection();
}
</script>

<template>
  <Panel
    position="top-left"
    class="m-2 flex flex-wrap gap-2 rounded-xl border border-ink-200 bg-white/95 p-2.5 shadow-2xl backdrop-blur-md dark:border-ink-500/80 dark:bg-ink-900/95"
  >
    <div class="flex flex-wrap items-center gap-1 border-r border-ink-200 pr-2.5 dark:border-ink-600">
      <span class="w-full text-[9px] font-semibold uppercase tracking-wider text-ink-500">Удалить</span>
      <button
        type="button"
        class="rounded-lg border border-red-200 bg-red-50 px-2.5 py-1.5 text-[11px] font-medium text-red-800 hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200 dark:hover:bg-red-900/50"
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
        class="rounded-lg border border-ink-200 px-2.5 py-1.5 text-[11px] text-ink-800 hover:bg-ink-100 dark:border-ink-600 dark:text-ink-200 dark:hover:bg-ink-800"
        title="Подогнать схему в кадр"
        @click="fitView({ padding: 0.25, duration: 280 })"
      >
        В кадр
      </button>
      <button
        type="button"
        class="rounded-lg border border-ink-200 px-2.5 py-1.5 text-[11px] text-ink-800 hover:bg-ink-100 dark:border-ink-600 dark:text-ink-200 dark:hover:bg-ink-800"
        @click="zoomIn()"
      >
        +
      </button>
      <button
        type="button"
        class="rounded-lg border border-ink-200 px-2.5 py-1.5 text-[11px] text-ink-800 hover:bg-ink-100 dark:border-ink-600 dark:text-ink-200 dark:hover:bg-ink-800"
        @click="zoomOut()"
      >
        −
      </button>
    </div>
  </Panel>
</template>
