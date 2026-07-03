<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSystemStatus } from '@/api/client'

const status = ref<any>({})
onMounted(async () => {
  try { status.value = await getSystemStatus() } catch (e) { console.error(e) }
})
</script>
<template>
  <div>
    <div class="mb-6 border-b border-slate-200 pb-5"><h1 class="text-2xl font-semibold text-slate-950">系统状态</h1></div>
    <div class="grid gap-4 md:grid-cols-2">
      <div v-for="(val, key) in status" :key="key" class="rounded-lg border border-slate-200 bg-white p-4">
        <p class="text-sm text-slate-500">{{ key }}</p>
        <p class="mt-2 font-semibold" :class="val === 'configured' || val === 'online' || val === 'ok' ? 'text-green-600' : 'text-slate-900'">{{ val }}</p>
      </div>
    </div>
  </div>
</template>
