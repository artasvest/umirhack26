<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, RouterView, useRouter } from "vue-router";
import { setToken } from "@/api/client";

const router = useRouter();
const isAdmin = computed(() => localStorage.getItem("studio_role") === "admin");

function logout(): void {
  setToken(null);
  localStorage.removeItem("studio_role");
  localStorage.removeItem("studio_name");
  void router.push("/login");
}
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="border-b border-ink-200 bg-white">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <nav class="flex gap-4 text-sm font-medium text-ink-900">
          <RouterLink to="/manager" class="hover:text-accent-dim" active-class="text-accent-dim">Заявки</RouterLink>
          <RouterLink v-if="isAdmin" to="/admin" class="hover:text-accent-dim">Админ-панель</RouterLink>
        </nav>
        <button type="button" class="text-sm text-ink-800/80 hover:text-ink-950" @click="logout">Выйти</button>
      </div>
    </header>
    <main class="mx-auto max-w-6xl px-4 py-8">
      <RouterView />
    </main>
  </div>
</template>
