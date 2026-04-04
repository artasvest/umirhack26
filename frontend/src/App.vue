<script setup lang="ts">
import { RouterView } from "vue-router";
import { useTheme } from "@/composables/useTheme";

const { isDark, toggle } = useTheme();
</script>

<template>
  <RouterView />
  <button
    type="button"
    class="fixed bottom-5 right-4 z-[100] flex min-h-11 items-center rounded-2xl border border-ink-200/90 bg-white/95 px-3.5 py-2.5 text-xs font-bold tracking-wide text-ink-800 shadow-glow-sm backdrop-blur-md transition hover:border-accent/40 hover:bg-white active:scale-[0.98] dark:border-ink-600/90 dark:bg-ink-800/95 dark:text-ink-100 dark:hover:border-accent/35 dark:hover:bg-ink-700 sm:bottom-6 sm:right-5 sm:px-4 sm:text-sm"
    :aria-label="isDark ? 'Включить светлую тему' : 'Включить тёмную тему'"
    @click="toggle"
  >
    {{ isDark ? "☀️ Светлая" : "🌙 Тёмная" }}
  </button>
</template>
