<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "@/api/client";

interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active?: boolean;
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
const togglingId = ref<string | null>(null);

function isActive(m: UserPublic): boolean {
  return m.is_active !== false;
}

async function setManagerActive(m: UserPublic, active: boolean): Promise<void> {
  if (isActive(m) === active) return;
  togglingId.value = m.id;
  error.value = "";
  try {
    await api(`/managers/${m.id}`, { method: "PATCH", json: { is_active: active } });
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось изменить статус";
  } finally {
    togglingId.value = null;
  }
}

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
            <th class="px-4 py-3">Доступ</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="m in managers"
            :key="m.id"
            class="border-b border-ink-200 bg-white text-ink-900 dark:border-ink-800/80 dark:bg-ink-950/40 dark:text-ink-100"
            :class="{ 'opacity-75': !isActive(m) }"
          >
            <td class="px-4 py-3 font-medium">
              {{ m.full_name }}
              <span
                v-if="!isActive(m)"
                class="ml-2 rounded-md bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900 dark:bg-amber-950/50 dark:text-amber-200"
              >
                заблокирован
              </span>
            </td>
            <td class="px-4 py-3 text-ink-600 dark:text-ink-300">{{ m.email }}</td>
            <td class="px-4 py-3">{{ statFor(m.id)?.in_progress_count ?? 0 }}</td>
            <td class="px-4 py-3">{{ statFor(m.id)?.completed_count ?? 0 }}</td>
            <td class="px-4 py-3">{{ statFor(m.id)?.conversion_percent ?? 0 }}</td>
            <td class="px-4 py-3">
              <button
                v-if="isActive(m)"
                type="button"
                class="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-800 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/50 dark:text-red-200 dark:hover:bg-red-950/40"
                :disabled="togglingId === m.id"
                @click="setManagerActive(m, false)"
              >
                {{ togglingId === m.id ? "…" : "Заблокировать" }}
              </button>
              <button
                v-else
                type="button"
                class="rounded-lg border border-emerald-200 px-3 py-1.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-50 disabled:opacity-50 dark:border-emerald-800/50 dark:text-emerald-200 dark:hover:bg-emerald-950/40"
                :disabled="togglingId === m.id"
                @click="setManagerActive(m, true)"
              >
                {{ togglingId === m.id ? "…" : "Разблокировать" }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
