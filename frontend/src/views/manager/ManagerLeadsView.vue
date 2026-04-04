<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { api, statusLabelRu, type LeadListItem, type LeadStatus } from "@/api/client";

const items = ref<LeadListItem[]>([]);
const statusFilter = ref<LeadStatus | "">("");
const error = ref("");

async function load(): Promise<void> {
  try {
    const q = statusFilter.value ? `?status=${statusFilter.value}` : "";
    items.value = await api<LeadListItem[]>(`/leads${q}`);
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Ошибка";
  }
}

onMounted(() => void load());

watch(statusFilter, () => void load());
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <h1 class="font-display text-2xl font-semibold text-ink-950">Заявки</h1>
      <label class="text-sm text-ink-800">
        Статус
        <select v-model="statusFilter" class="ml-2 rounded-lg border border-ink-200 px-2 py-1">
          <option value="">Все</option>
          <option value="pending">Ожидает</option>
          <option value="in_progress">В обработке</option>
          <option value="completed">Завершена</option>
        </select>
      </label>
    </div>
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <div class="overflow-x-auto rounded-xl border border-ink-200 bg-white shadow-card">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-ink-200 bg-ink-50 text-ink-800/80">
          <tr>
            <th class="px-4 py-3 font-medium">Имя</th>
            <th class="px-4 py-3 font-medium">Телефон</th>
            <th class="px-4 py-3 font-medium">Тип</th>
            <th class="px-4 py-3 font-medium">Бюджет</th>
            <th class="px-4 py-3 font-medium">Статус</th>
            <th class="px-4 py-3 font-medium">Дата</th>
            <th class="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in items" :key="row.id" class="border-b border-ink-100 hover:bg-ink-50/50">
            <td class="px-4 py-3 font-medium text-ink-900">{{ row.name }}</td>
            <td class="px-4 py-3 font-mono text-xs">{{ row.phone }}</td>
            <td class="px-4 py-3">{{ row.room_type || "—" }}</td>
            <td class="px-4 py-3">{{ row.budget || "—" }}</td>
            <td class="px-4 py-3">{{ statusLabelRu(row.status) }}</td>
            <td class="px-4 py-3 text-ink-800/70">{{ new Date(row.created_at).toLocaleString() }}</td>
            <td class="px-4 py-3">
              <RouterLink :to="`/manager/leads/${row.id}`" class="text-accent-dim hover:underline">Открыть</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!items.length && !error" class="p-6 text-center text-ink-800/60">Нет заявок</p>
    </div>
  </div>
</template>
