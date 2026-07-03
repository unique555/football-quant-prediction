<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getStats, getPerformance } from '@/api/client'
const statsData = ref<any>({})
const perfData = ref<any>({})
onMounted(async () => {
  try { const [s,p] = await Promise.all([getStats(), getPerformance()]); statsData.value=s; perfData.value=p } catch(e){}
})
</script>
<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-xl font-bold tracking-tight text-surface-900">统计</h1>
      <p class="mt-0.5 text-xs text-surface-500">分析性能与收益概览</p>
    </div>
    <div class="grid gap-3 sm:grid-cols-3">
      <div class="rounded-xl border border-surface-100 bg-white p-4 shadow-card">
        <p class="text-xs font-medium text-surface-500">总预测</p>
        <p class="mt-2 text-2xl font-bold text-surface-900">{{ statsData.total_predictions || 0 }}</p>
      </div>
      <div class="rounded-xl border border-surface-100 bg-white p-4 shadow-card">
        <p class="text-xs font-medium text-surface-500">命中率</p>
        <p class="mt-2 text-2xl font-bold text-success-600">{{ ((perfData.overall?.hit_rate||0)*100).toFixed(1) }}%</p>
      </div>
      <div class="rounded-xl border border-surface-100 bg-white p-4 shadow-card">
        <p class="text-xs font-medium text-surface-500">总收益</p>
        <p class="mt-2 text-2xl font-bold" :class="(perfData.overall?.profit_units||0)>=0?'text-success-600':'text-danger-600'">{{ (perfData.overall?.profit_units||0).toFixed(2) }}u</p>
      </div>
    </div>
  </div>
</template>
