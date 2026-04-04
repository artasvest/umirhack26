<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "@/api/client";

interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  role: string;
}

interface ManagerStats {
  id: string;
  email: string;
  full_name: string;
  in_progress_count: number;
  completed_count: number;
  conversion_percent: number;
}

const managers = ref<UserPublic[]>([]);
const stats = ref<ManagerStats[]>([]);
const error = ref("");
const name = ref("");
const email = ref("");
const password = ref("");
const creating = ref(false);

async function load(): Promise<void> {
  try {
    managers.value = await api<UserPublic[]>("/managers");
    stats.value = await api<ManagerStats[]>("/managers/stats");
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
  }
}

onMounted(() => void load());

async function createManager(): Promise<void> {
  creating.value = true;
  try {
    await api("/managers", {
      method: "POST",
      json: { full_name: name.value.trim(), email: email.value.trim(), password: password.value },
    });
    name.value = "";
    email.value = "";
    password.value = "";
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не создан";
  } finally {
    creating.value = false;
  }
}

function statFor(id: string): ManagerStats | undefined {
  return stats.value.find((s) => s.id === id);
}
</script>

<template>
  <div class="space-y-8">
    <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-white">Менеджеры</h1>
    <p v-if="error" class="text-red-600 dark:text-red-400">{{ error }}</p>

    <div class="rounded-2xl border border-ink-200 bg-white p-6 dark:border-ink-800 dark:bg-ink-900/50">
      <h2 class="font-display text-lg font-semibold text-ink-950 dark:text-white">Новый менеджер</h2>
      <div class="mt-4 grid gap-3 sm:grid-cols-3">
        <input
          v-model="name"
          type="text"
          placeholder="Имя"
          class="rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-950 dark:border-ink-700 dark:bg-ink-950 dark:text-white"
        />
        <input
          v-model="email"
          type="email"
          placeholder="Email"
          class="rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-950 dark:border-ink-700 dark:bg-ink-950 dark:text-white"
        />
        <input
          v-model="password"
          type="password"
          placeholder="Пароль"
          class="rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-950 dark:border-ink-700 dark:bg-ink-950 dark:text-white"
        />
      </div>
      <button
        type="button"
        class="mt-4 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-ink-950 hover:bg-accent-dim disabled:opacity-50"
        :disabled="creating"
        @click="createManager"
      >
        Создать
      </button>
    </div>

    <div class="overflow-x-auto rounded-2xl border border-ink-200 dark:border-ink-800">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-ink-200 bg-ink-100 text-ink-700 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-400">
          <tr>
            <th class="px-4 py-3">Имя</th>
            <th class="px-4 py-3">Email</th>
            <th class="px-4 py-3">В работе</th>
            <th class="px-4 py-3">Завершено</th>
            <th class="px-4 py-3">Конверсия %</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="m in managers"
            :key="m.id"
            class="border-b border-ink-200 bg-white text-ink-900 dark:border-ink-800/80 dark:bg-ink-950/40 dark:text-ink-100"
          >
            <td class="px-4 py-3 font-medium">{{ m.full_name }}</td>
            <td class="px-4 py-3 text-ink-600 dark:text-ink-300">{{ m.email }}</td>
            <td class="px-4 py-3">{{ statFor(m.id)?.in_progress_count ?? 0 }}</td>
            <td class="px-4 py-3">{{ statFor(m.id)?.completed_count ?? 0 }}</td>
            <td class="px-4 py-3">{{ statFor(m.id)?.conversion_percent ?? 0 }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
