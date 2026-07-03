<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getValueToday } from '@/api/client'

const bets = ref<any[]>([])
const loading = ref(true)
onMounted(async () => {
  try { bets.value = await getValueToday(30) } catch (e) { console.error(e) }
  finally { loading.value = false }
})

const fmtDate = (d: string | null) => d ? new Date(d).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '?'
</script>
<template>
  <div>
    <div class="mb-6 border-b border-slate-200 pb-5"><h1 class="text-2xl font-semibold text-slate-950">价值投注</h1><p class="mt-1 text-sm text-slate-600">系统自动筛选的 Edge &gt; 3% 的价值投注，含 Kelly 注额建议</p></div>
    <div v-if="loading" class="py-20 text-center text-slate-500">加载中...</div>
    <div v-else-if="!bets.length" class="py-20 text-center text-slate-400"><p class="text-lg">🏆</p><p class="text-sm">暂无价值投注</p></div>
    <div v-else class="space-y-3">
      <p class="text-sm text-slate-600">共 <span class="font-semibold text-slate-950">{{ bets.length }}</span> 场价值投注</p>
      <div v-for="bet in bets" :key="bet.id || bet.fixture_id" class="rounded-lg border border-slate-200 bg-white p-4">
        <div class="flex items-start justify-between">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 text-xs text-slate-500"><span class="rounded bg-slate-100 px-1.5 py-0.5">{{ bet.league || '?' }}</span><span>{{ fmtDate(bet.kickoff) }}</span></div>
            <p class="mt-1 font-semibold text-slate-950">{{ bet.home_team }} <span class="text-slate-400">vs</span> {{ bet.away_team }}</p>
            <p class="mt-0.5 text-sm text-slate-600">推荐：<span class="font-medium">{{ bet.best_pick || '?' }}</span> @ {{ bet.best_odds }}</p>
          </div>
          <span class="rounded px-2 py-0.5 text-xs font-medium" :class="bet.risk==='低'?'bg-green-50 text-green-700':bet.risk==='高'?'bg-red-50 text-red-700':'bg-amber-50 text-amber-700'">{{ bet.risk || '?' }}</span>
        </div>
        <div class="mt-3 grid grid-cols-4 gap-2 border-t border-slate-100 pt-3">
          <div class="text-center"><p class="text-xs text-slate-400">Edge</p><p class="text-sm font-semibold" :class="(bet.best_edge||0)>0?'text-green-600':'text-slate-700'">{{ ((bet.best_edge||0)*100).toFixed(1) }}%</p></div>
          <div class="text-center"><p class="text-xs text-slate-400">EV</p><p class="text-sm font-semibold" :class="(bet.best_ev||0)>0?'text-green-600':'text-slate-700'">{{ ((bet.best_ev||0)*100).toFixed(1) }}%</p></div>
          <div class="text-center"><p class="text-xs text-slate-400">Kelly</p><p class="text-sm font-semibold text-green-600">{{ ((bet.best_kelly||0)*100).toFixed(1) }}%</p></div>
          <div class="text-center"><p class="text-xs text-slate-400">价值分</p><p class="text-sm font-semibold" :class="(bet.value_score||0)>=60?'text-green-600':'text-slate-700'">{{ bet.value_score || 0 }}/100</p></div>
        </div>
      </div>
    </div>
  </div>
</template>
