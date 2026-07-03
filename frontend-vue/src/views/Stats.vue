<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getStats, getPerformance, getProfitCurve } from '@/api/client'

const statsData = ref<any>({})
const perfData = ref<any>({})
const profitData = ref<any[]>([])

onMounted(async () => {
  try {
    const [s, p, c] = await Promise.all([getStats(), getPerformance(), getProfitCurve()])
    statsData.value = s; perfData.value = p; profitData.value = c
  } catch (e) { console.error(e) }
})
</script>
<template>
  <div>
    <div class="mb-6 border-b border-slate-200 pb-5"><h1 class="text-2xl font-semibold text-slate-950">统计</h1><p class="mt-1 text-sm text-slate-600">分析性能与收益</p></div>
    <div class="grid gap-4 md:grid-cols-3">
      <div class="rounded-lg border border-slate-200 bg-white p-4"><p class="text-sm text-slate-500">总预测</p><p class="mt-3 text-2xl font-semibold">{{ statsData.total_predictions || 0 }}</p></div>
      <div class="rounded-lg border border-slate-200 bg-white p-4"><p class="text-sm text-slate-500">命中率</p><p class="mt-3 text-2xl font-semibold">{{ ((perfData.overall?.hit_rate || 0) * 100).toFixed(1) }}%</p></div>
      <div class="rounded-lg border border-slate-200 bg-white p-4"><p class="text-sm text-slate-500">总收益</p><p class="mt-3 text-2xl font-semibold" :class="(perfData.overall?.profit_units||0)>=0?'text-green-600':'text-red-600'">{{ (perfData.overall?.profit_units || 0).toFixed(2) }}u</p></div>
    </div>
    <div v-if="profitData.length" class="mt-6 rounded-lg border border-slate-200 bg-white p-6">
      <h2 class="mb-4 font-semibold">📈 收益曲线</h2>
      <div class="h-[300px] overflow-x-auto">
        <div class="flex items-end gap-1" style="min-width: 400px; height: 250px;">
          <div v-for="(point, i) in profitData" :key="i" class="flex-1 flex flex-col items-center justify-end" :style="{ height: '100%' }">
            <div class="w-full rounded-t" :style="{ height: Math.max(0, (point.profit / Math.max(...profitData.map(p=>p.profit))) * 200) + 'px', background: point.profit >= 0 ? '#059669' : '#dc2626' }"></div>
          </div>
        </div>
        <div class="text-xs text-slate-500">x轴: 时间顺序 | y轴: 累积收益</div>
      </div>
    </div>
  </div>
</template>
