<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSystemStatus } from '@/api/client'
const status = ref<any>({})
onMounted(async () => {
  try { status.value = await getSystemStatus() } catch(e){}
})
const statusClass = (v: string) => v === 'configured' || v === 'online' || v === 'ok' ? 'bg-success-50 text-success-600 border-success-200' : 'bg-surface-100 text-surface-500 border-surface-200'
</script>
<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-xl font-bold tracking-tight text-surface-900">系统状态</h1>
      <p class="mt-0.5 text-xs text-surface-500">服务健康与配置状态</p>
    </div>
    <div class="grid gap-3 sm:grid-cols-2">
      <div v-for="(val,key) in status" :key="key" class="flex items-center justify-between rounded-xl border border-surface-100 bg-white p-4 shadow-card">
        <span class="text-sm font-medium text-surface-700">{{ key }}</span>
        <span class="rounded-md border px-3 py-1 text-xs font-medium" :class="statusClass(val)">{{ val }}</span>
      </div>
    </div>
  </div>
</template>
