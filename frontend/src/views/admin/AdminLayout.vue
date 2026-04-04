<script setup lang="ts">
import { onUnmounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { requestTelegramLink, setToken } from "@/api/client";

const router = useRouter();
const route = useRoute();

const mobileMenuOpen = ref(false);
const telegramLinkLoading = ref(false);
const telegramLinkError = ref<string | null>(null);

async function openTelegramLink(): Promise<void> {
  telegramLinkError.value = null;
  telegramLinkLoading.value = true;
  try {
    const { url } = await requestTelegramLink();
    window.open(url, "_blank", "noopener,noreferrer");
    closeMobileMenu();
  } catch (e) {
    telegramLinkError.value = e instanceof Error ? e.message : "Не удалось получить ссылку";
  } finally {
    telegramLinkLoading.value = false;
  }
}

const navLinks = [
  { to: "/admin", label: "Обзор" },
  { to: "/admin/leads", label: "Заявки" },
  { to: "/admin/managers", label: "Менеджеры" },
  { to: "/admin/analytics", label: "Аналитика" },
  { to: "/admin/quizzes", label: "Квизы" },
  { to: "/admin/quiz", label: "Конструктор" },
] as const;

function closeMobileMenu(): void {
  mobileMenuOpen.value = false;
}

function toggleMobileMenu(): void {
  mobileMenuOpen.value = !mobileMenuOpen.value;
}

function logout(): void {
  closeMobileMenu();
  setToken(null);
  localStorage.removeItem("studio_role");
  localStorage.removeItem("studio_name");
  localStorage.removeItem("studio_user_id");
  void router.push("/login");
}

watch(
  () => route.fullPath,
  () => {
    closeMobileMenu();
  },
);

watch(mobileMenuOpen, (open) => {
  document.body.style.overflow = open ? "hidden" : "";
  if (!open) return;
  const onKey = (e: KeyboardEvent): void => {
    if (e.key === "Escape") closeMobileMenu();
  };
  document.addEventListener("keydown", onKey);
  return () => document.removeEventListener("keydown", onKey);
});

onUnmounted(() => {
  document.body.style.overflow = "";
});
</script>

<template>
  <div class="page-shell text-ink-950 dark:text-ink-50">
    <!-- Мобильное: полоска + кнопка «Меню» -->
    <header class="app-header md:hidden">
      <div class="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
        <RouterLink
          to="/admin"
          class="min-w-0 font-display text-base font-bold tracking-tight text-ink-950 dark:text-white"
          @click="closeMobileMenu"
        >
          Админ-панель
        </RouterLink>
        <button
          type="button"
          class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-ink-200 bg-white/90 text-ink-800 shadow-sm transition active:scale-[0.97] dark:border-ink-600 dark:bg-ink-800/90 dark:text-ink-100"
          :aria-expanded="mobileMenuOpen"
          aria-controls="admin-mobile-drawer"
          aria-label="Открыть меню"
          @click="toggleMobileMenu"
        >
          <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path v-if="!mobileMenuOpen" stroke-linecap="round" d="M4 7h16M4 12h16M4 17h16" />
            <path v-else stroke-linecap="round" d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
    </header>

    <!-- Десктоп: обычный хедер -->
    <header class="app-header hidden md:block">
      <div class="mx-auto max-w-6xl px-4 py-3 sm:px-6 lg:px-8">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <nav
            class="-mx-1 flex gap-1 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:gap-2 sm:overflow-visible sm:pb-0 [&::-webkit-scrollbar]:hidden"
          >
            <RouterLink
              v-for="link in navLinks"
              :key="link.to"
              :to="link.to"
              class="shrink-0 rounded-full px-3 py-2 text-sm font-semibold text-ink-700 transition hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-800"
              active-class="!bg-accent/20 !text-ink-950 ring-1 ring-accent/40 dark:!text-accent"
            >
              {{ link.label }}
            </RouterLink>
          </nav>
          <div class="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:gap-2">
            <button
              type="button"
              class="shrink-0 rounded-full px-3 py-2 text-sm font-semibold text-ink-800 ring-1 ring-ink-200 transition hover:bg-ink-100 dark:text-ink-100 dark:ring-ink-600 dark:hover:bg-ink-800"
              :disabled="telegramLinkLoading"
              @click="openTelegramLink"
            >
              {{ telegramLinkLoading ? "Ссылка…" : "Войти в Telegram" }}
            </button>
            <p v-if="telegramLinkError" class="text-xs text-red-600 dark:text-red-400 sm:max-w-xs">
              {{ telegramLinkError }}
            </p>
            <button
              type="button"
              class="shrink-0 rounded-full px-3 py-2 text-sm font-medium text-ink-600 transition hover:bg-ink-100 hover:text-ink-950 dark:text-ink-400 dark:hover:bg-ink-800 dark:hover:text-white"
              @click="logout"
            >
              Выйти
            </button>
          </div>
        </div>
      </div>
    </header>

    <Teleport to="body">
      <div
        v-show="mobileMenuOpen"
        id="admin-mobile-drawer"
        class="fixed inset-0 z-[190] md:hidden"
        role="dialog"
        aria-modal="true"
        aria-label="Навигация"
      >
        <button
          type="button"
          class="absolute inset-0 bg-ink-950/55 backdrop-blur-[2px]"
          aria-label="Закрыть меню"
          @click="closeMobileMenu"
        />
        <nav
          class="absolute inset-y-0 right-0 flex w-[min(100%,20rem)] flex-col border-l border-ink-200/90 bg-white/98 shadow-2xl backdrop-blur-xl dark:border-ink-700 dark:bg-ink-900/98"
          @click.stop
        >
          <div class="flex items-center justify-between border-b border-ink-200 px-4 py-3 dark:border-ink-700">
            <span class="font-display text-sm font-bold text-ink-950 dark:text-white">Меню</span>
            <button
              type="button"
              class="flex h-10 w-10 items-center justify-center rounded-lg text-ink-600 transition hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-800"
              aria-label="Закрыть"
              @click="closeMobileMenu"
            >
              <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
          <div class="flex flex-1 flex-col gap-0.5 overflow-y-auto p-3 pb-6">
            <RouterLink
              v-for="link in navLinks"
              :key="`m-${link.to}`"
              :to="link.to"
              class="rounded-xl px-4 py-3.5 text-base font-semibold text-ink-800 transition active:bg-ink-100 dark:text-ink-100 dark:active:bg-ink-800"
              active-class="!bg-accent/20 !text-ink-950 ring-1 ring-accent/35 dark:!text-accent"
              @click="closeMobileMenu"
            >
              {{ link.label }}
            </RouterLink>
          </div>
          <div class="border-t border-ink-200 p-3 dark:border-ink-700">
            <button
              type="button"
              class="mb-2 w-full rounded-xl border border-ink-200 bg-white py-3.5 text-base font-semibold text-ink-800 transition active:bg-ink-100 dark:border-ink-600 dark:bg-ink-800 dark:text-ink-100 dark:active:bg-ink-700"
              :disabled="telegramLinkLoading"
              @click="openTelegramLink"
            >
              {{ telegramLinkLoading ? "Ссылка…" : "Войти в Telegram" }}
            </button>
            <p v-if="telegramLinkError" class="mb-2 text-sm text-red-600 dark:text-red-400">
              {{ telegramLinkError }}
            </p>
            <button
              type="button"
              class="w-full rounded-xl border border-ink-200 bg-ink-50 py-3.5 text-base font-semibold text-ink-800 transition active:bg-ink-100 dark:border-ink-600 dark:bg-ink-800 dark:text-ink-100 dark:active:bg-ink-700"
              @click="logout"
            >
              Выйти
            </button>
          </div>
        </nav>
      </div>
    </Teleport>

    <main class="content-container">
      <RouterView />
    </main>
  </div>
</template>
