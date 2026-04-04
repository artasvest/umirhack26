<script setup lang="ts">
import { RouterLink, RouterView, useRouter } from "vue-router";
import { setToken } from "@/api/client";

const router = useRouter();

function logout(): void {
  setToken(null);
  localStorage.removeItem("studio_role");
  localStorage.removeItem("studio_name");
  void router.push("/login");
}
</script>

<template>
  <div class="min-h-screen bg-ink-950 text-ink-50">
    <header class="border-b border-ink-800 bg-ink-900/80 backdrop-blur">
      <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-3">
        <nav class="flex flex-wrap gap-4 text-sm font-medium">
          <RouterLink to="/admin" class="hover:text-accent" active-class="text-accent">Обзор</RouterLink>
          <RouterLink to="/admin/managers" class="hover:text-accent" active-class="text-accent">Менеджеры</RouterLink>
          <RouterLink to="/admin/analytics" class="hover:text-accent" active-class="text-accent">Аналитика</RouterLink>
          <RouterLink to="/admin/quiz" class="hover:text-accent" active-class="text-accent">Конструктор квиза</RouterLink>
          <RouterLink to="/manager" class="hover:text-accent">Кабинет менеджера</RouterLink>
        </nav>
        <button type="button" class="text-sm text-ink-300 hover:text-white" @click="logout">Выйти</button>
      </div>
    </header>
    <main class="mx-auto max-w-6xl px-4 py-8">
      <RouterView />
    </main>
  </div>
</template>
