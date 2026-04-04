<script setup lang="ts">
import { ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { loginRequest, setToken } from "@/api/client";

const router = useRouter();
const route = useRoute();
const email = ref("");
const password = ref("");
const error = ref("");
const loading = ref(false);

async function onSubmit(): Promise<void> {
  error.value = "";
  loading.value = true;
  try {
    const res = await loginRequest(email.value.trim(), password.value);
    setToken(res.access_token);
    localStorage.setItem("studio_role", res.role);
    localStorage.setItem("studio_name", res.full_name);
    const redir = (route.query.redirect as string) || "";
    if (res.role === "admin") {
      await router.replace(redir.startsWith("/admin") ? redir : "/admin");
    } else {
      await router.replace(redir.startsWith("/manager") ? redir : "/manager");
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка входа";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-ink-50 px-4">
    <form class="w-full max-w-sm space-y-4 rounded-2xl border border-ink-200 bg-white p-8 shadow-lift" @submit.prevent="onSubmit">
      <h1 class="font-display text-xl font-semibold text-ink-950">Вход</h1>
      <p class="text-sm text-ink-800/70">Менеджер или администратор</p>
      <label class="block text-sm font-medium text-ink-800">
        Email
        <input v-model="email" type="email" required class="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 outline-none focus:border-accent" autocomplete="username" />
      </label>
      <label class="block text-sm font-medium text-ink-800">
        Пароль
        <input v-model="password" type="password" required class="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 outline-none focus:border-accent" autocomplete="current-password" />
      </label>
      <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      <button type="submit" class="w-full rounded-xl bg-ink-950 py-2.5 font-semibold text-white hover:bg-ink-900 disabled:opacity-50" :disabled="loading">
        {{ loading ? "Вход…" : "Войти" }}
      </button>
      <RouterLink to="/" class="block text-center text-sm text-accent-dim hover:underline">На главную</RouterLink>
    </form>
  </div>
</template>
