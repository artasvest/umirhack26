<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { api, statusLabelRu, type LeadListItem, type LeadStatus } from "@/api/client";
import { formatDateTimeMsk } from "@/utils/cabinetTime";

interface UserPublic {
  id: string;
  email: string;
  full_name: string;
}

const managers = ref<UserPublic[]>([]);
const items = ref<LeadListItem[]>([]);
const statusFilter = ref<LeadStatus | "">("");
const onlyPool = ref(false);
const filterManagerId = ref("");
const error = ref("");
const busyId = ref<string | null>(null);

const managerOptions = computed(() => managers.value);

async function loadManagers(): Promise<void> {
  try {
    managers.value = await api<UserPublic[]>("/managers");
  } catch {
    managers.value = [];
  }
}

function listQuery(): string {
  const p = new URLSearchParams();
  if (onlyPool.value) {
    p.set("only_pool", "true");
  } else {
    if (statusFilter.value) p.set("status", statusFilter.value);
    if (filterManagerId.value) p.set("assigned_manager_id", filterManagerId.value);
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function loadLeads(): Promise<void> {
  error.value = "";
  try {
    items.value = await api<LeadListItem[]>(`/leads${listQuery()}`);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
    items.value = [];
  }
}

async function load(): Promise<void> {
  await loadManagers();
  await loadLeads();
}

onMounted(() => void load());

watch([statusFilter, onlyPool, filterManagerId], () => void loadLeads());

const showPoolWaitColumn = computed(() => onlyPool.value || statusFilter.value === "pending");

function poolSince(row: LeadListItem): string {
  if (row.status !== "pending" || row.assigned_manager_id) return "—";
  const t = row.pool_entered_at || row.created_at;
  return t ? formatDateTimeMsk(t) : "—";
}

async function patchLead(id: string, body: Record<string, unknown>): Promise<void> {
  busyId.value = id;
  error.value = "";
  try {
    await api(`/leads/${id}/admin`, { method: "PATCH", json: body });
    await loadLeads();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
  } finally {
    busyId.value = null;
  }
}

function toPool(id: string): void {
  void patchLead(id, { status: "pending" });
}

function completeLead(id: string): void {
  void patchLead(id, { status: "completed" });
}

function assignTo(id: string, managerId: string): void {
  if (!managerId) return;
  void patchLead(id, { assigned_manager_id: managerId });
}

function onAssignSelect(leadId: string, ev: Event): void {
  const v = (ev.target as HTMLSelectElement).value;
  (ev.target as HTMLSelectElement).value = "";
  if (!v) return;
  if (v === "__pool__") {
    toPool(leadId);
    return;
  }
  assignTo(leadId, v);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="font-display text-2xl font-semibold text-ink-950 dark:text-white">Заявки</h1>
    <p class="max-w-3xl text-sm text-ink-600 dark:text-ink-400">
      Общий пул, назначения и статусы. Менеджер сам берёт до 5 заявок; вы можете назначить сверх лимита, вернуть в пул или
      завершить.
    </p>
    <p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>

    <div class="flex flex-wrap items-end gap-4 rounded-2xl border border-ink-200 bg-ink-50 p-4 dark:border-ink-700 dark:bg-ink-900/40">
      <label class="text-sm text-ink-800 dark:text-ink-200">
        <input v-model="onlyPool" type="checkbox" class="mr-2 align-middle" />
        Только общий пул
      </label>
      <label v-if="!onlyPool" class="text-sm text-ink-800 dark:text-ink-200">
        Статус
        <select
          v-model="statusFilter"
          class="ml-2 rounded-lg border border-ink-200 bg-white px-2 py-1 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-100"
        >
          <option value="">Все</option>
          <option value="pending">Ожидает</option>
          <option value="in_progress">В работе</option>
          <option value="completed">Завершена</option>
        </select>
      </label>
      <label v-if="!onlyPool" class="text-sm text-ink-800 dark:text-ink-200">
        Менеджер
        <select
          v-model="filterManagerId"
          class="ml-2 rounded-lg border border-ink-200 bg-white px-2 py-1 dark:border-ink-600 dark:bg-ink-950 dark:text-ink-100"
        >
          <option value="">Все</option>
          <option v-for="m in managerOptions" :key="m.id" :value="m.id">{{ m.full_name }}</option>
        </select>
      </label>
      <button
        type="button"
        class="rounded-xl border border-ink-200 bg-white px-3 py-1.5 text-sm dark:border-ink-600 dark:bg-ink-900"
        @click="load()"
      >
        Обновить
      </button>
    </div>

    <div class="overflow-x-auto rounded-2xl border border-ink-200 bg-white dark:border-ink-800 dark:bg-ink-900/50">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-ink-200 bg-ink-100 text-ink-700 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-400">
          <tr>
            <th class="px-3 py-3 font-medium">Заявка / имя</th>
            <th class="px-3 py-3 font-medium">Телефон</th>
            <th class="px-3 py-3 font-medium">Статус</th>
            <th class="px-3 py-3 font-medium">Менеджер</th>
            <th v-if="showPoolWaitColumn" class="px-3 py-3 font-medium">В пуле с</th>
            <th class="px-3 py-3 font-medium">Создана</th>
            <th class="px-3 py-3 font-medium">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in items"
            :key="row.id"
            class="border-b border-ink-200 dark:border-ink-800/80"
          >
            <td class="px-3 py-2">
              <RouterLink :to="`/manager/leads/${row.id}`" class="font-medium text-accent-dim hover:underline">{{
                row.name
              }}</RouterLink>
            </td>
            <td class="px-3 py-2 font-mono text-xs">{{ row.phone }}</td>
            <td class="px-3 py-2">{{ statusLabelRu(row.status) }}</td>
            <td class="px-3 py-2 text-ink-600 dark:text-ink-400">
              {{ row.assigned_manager_name || "—" }}
            </td>
            <td v-if="showPoolWaitColumn" class="px-3 py-2 text-xs text-ink-600 dark:text-ink-400">
              {{ poolSince(row) }}
            </td>
            <td class="px-3 py-2 text-xs text-ink-500">{{ formatDateTimeMsk(row.created_at) }}</td>
            <td class="px-3 py-2">
              <div class="flex flex-wrap items-center gap-2">
                <select
                  class="max-w-[160px] rounded-lg border border-ink-200 bg-white px-1 py-1 text-xs dark:border-ink-600 dark:bg-ink-950"
                  :disabled="busyId === row.id"
                  @change="onAssignSelect(row.id, $event)"
                >
                  <option value="">Назначить…</option>
                  <option value="__pool__">В общий пул</option>
                  <option v-for="m in managerOptions" :key="m.id" :value="m.id">{{ m.full_name }}</option>
                </select>
                <button
                  type="button"
                  class="rounded-lg border border-ink-200 px-2 py-1 text-xs dark:border-ink-600"
                  :disabled="busyId === row.id || row.status === 'completed'"
                  @click="completeLead(row.id)"
                >
                  Завершить
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!items.length && !error" class="p-6 text-center text-ink-500">Нет заявок</p>
    </div>
  </div>
</template>
