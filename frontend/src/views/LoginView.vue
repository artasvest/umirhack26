<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { loginRequest, setToken } from "@/api/client";

const router = useRouter();
const route = useRoute();
const email = ref("");
const password = ref("");
const error = ref("");
const loading = ref(false);

const blockedByAdmin = computed(() => route.query.blocked === "1");

watch(
  () => route.query.blocked,
  (v) => {
    if (v === "1") error.value = "";
  },
);

async function onSubmit(): Promise<void> {
  error.value = "";
  loading.value = true;
  try {
    setToken(null);
    const res = await loginRequest(email.value.trim(), password.value);
    setToken(res.access_token);
    localStorage.setItem("studio_role", res.role);
    localStorage.setItem("studio_name", res.full_name);
    localStorage.setItem("studio_user_id", res.user_id);
    const redir = (route.query.redirect as string) || "";
    if (res.role === "admin") {
      await router.replace(redir.startsWith("/admin") ? redir : "/admin/analytics");
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
  <div class="page-shell flex min-h-screen items-center justify-center px-4 py-10 sm:px-6 sm:py-12">
    <form
      class="surface-panel w-full max-w-md !p-6 space-y-5 shadow-glow ring-1 ring-accent/15 dark:ring-accent/10 sm:!p-9 sm:space-y-6"
      @submit.prevent="onSubmit"
    >
      <div class="space-y-1 text-center sm:text-left">
        <h1 class="font-display text-2xl font-bold tracking-tight text-ink-950 dark:text-ink-50 sm:text-3xl">Вход</h1>
        <p class="text-sm text-ink-600 dark:text-ink-400">Менеджер или администратор</p>
      </div>
      <div
        v-if="blockedByAdmin"
        class="rounded-xl border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/35 dark:text-amber-100"
        role="alert"
      >
        <p class="font-semibold">Доступ ограничен</p>
        <p class="mt-1 text-amber-900/90 dark:text-amber-200/95">
          Ваш аккаунт заблокирован. Войти нельзя — обратитесь к администратору.
        </p>
      </div>
      <label class="block text-sm font-semibold text-ink-800 dark:text-ink-200">
        Email
        <input
          v-model="email"
          type="email"
          required
          class="mt-2 min-h-11 w-full rounded-xl border border-ink-200 bg-white px-4 py-2.5 text-ink-950 shadow-sm outline-none ring-accent/0 transition focus:border-accent focus:ring-2 focus:ring-accent/30 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50"
          autocomplete="username"
        />
      </label>
      <label class="block text-sm font-semibold text-ink-800 dark:text-ink-200">
        Пароль
        <input
          v-model="password"
          type="password"
          required
          class="mt-2 min-h-11 w-full rounded-xl border border-ink-200 bg-white px-4 py-2.5 text-ink-950 shadow-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/30 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-50"
          autocomplete="current-password"
        />
      </label>
      <p v-if="error" class="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200">
        {{ error }}
      </p>
      <button
        type="submit"
        class="min-h-12 w-full rounded-xl bg-ink-950 py-3 text-base font-bold text-white shadow-lg shadow-ink-900/20 transition hover:bg-ink-900 active:scale-[0.99] disabled:opacity-50 dark:bg-accent dark:text-ink-950 dark:shadow-accent/20 dark:hover:bg-accent-dim"
        :disabled="loading"
      >
        {{ loading ? "Вход…" : "Войти" }}
      </button>
      <RouterLink
        to="/"
        class="block text-center text-sm font-semibold text-accent-dim transition hover:text-accent hover:underline"
      >
        На главную
      </RouterLink>
    </form>
  </div>
</template>
