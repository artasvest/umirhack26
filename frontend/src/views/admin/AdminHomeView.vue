<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <div class="space-y-4">
    <h1 class="font-display text-2xl font-semibold">Админ-панель</h1>
    <p class="max-w-xl text-ink-300">Управление менеджерами, аналитика воронки и экспорт заявок, JSON-схема квиза для будущего Vue Flow.</p>
    <ul class="flex flex-col gap-2 text-accent">
      <li><RouterLink class="hover:underline" to="/admin/managers">Менеджеры и статистика</RouterLink></li>
      <li><RouterLink class="hover:underline" to="/admin/analytics">Аналитика и CSV</RouterLink></li>
      <li><RouterLink class="hover:underline" to="/admin/quiz">Конструктор квиза</RouterLink></li>
    </ul>
  </div>
</template>
