<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getValueToday } from '@/api/client'

const bets = ref<any[]>([])
onMounted(async () => {
  try { bets.value = await getValueToday(50) } catch (e) { console.error(e) }
})

const fmtDate = (d: string | null) => d ? new Date(d).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '?'
const riskClass = (r: string | null) => r === '低' ? 'bg-success-50 text-success-600 border-success-200' : r === '高' ? 'bg-danger-50 text-danger-600 border-danger-200' : 'bg-warning-50 text-warning-600 border-warning-200'
</script>
<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <div><h1 class="text-xl font-bold tracking-tight text-surface-900">🏆 价值投注</h1><p class="mt-0.5 text-xs text-surface-500">系统自动筛选 Edge &gt; 3% 的价值投注 · 含 Kelly 注额建议</p></div>
      <span class="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">{{ bets.length }} 场</span>
    </div>
    <div v-if="!bets.length" class="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-surface-200 bg-white py-16 text-surface-400"><span class="text-3xl mb-2">🏆</span><p class="text-sm font-medium">暂无价值投注</p><p class="mt-1 text-xs">系统每 3 小时自动筛选，有 Edge 信号时自动推送</p></div>
    <div v-else class="grid gap-3">
      <div v-for="bet in bets" :key="bet.fixture_id" class="group rounded-xl border border-surface-100 bg-white p-4 shadow-card hover:shadow-card-hover transition-all">
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 text-[11px] text-surface-500">
              <span class="rounded-md bg-surface-100 px-2 py-0.5 font-medium">{{ bet.league || '?' }}</span>
              <span>{{ fmtDate(bet.kickoff) }}</span>
            </div>
            <router-link :to="'/matches/'+bet.fixture_id" class="mt-1.5 block text-sm font-semibold text-surface-900 hover:text-indigo-600 transition-colors">{{ bet.home_team }} <span class="text-surface-300">vs</span> {{ bet.away_team }}</router-link>
            <div class="mt-2 flex flex-wrap items-center gap-2">
              <span class="rounded-md bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">{{ bet.best_display_pick || bet.best_pick || '?' }}</span>
              <span class="text-xs text-surface-500">@ {{ bet.best_odds }}</span>
              <span class="text-xs text-surface-400">·</span>
              <span class="rounded-md px-2 py-0.5 text-[11px] font-medium border" :class="riskClass(bet.risk)">{{ bet.risk || '中' }}风险</span>
            </div>
          </div>
          <div class="shrink-0 text-right">
            <p class="text-lg font-bold" :class="(bet.best_edge||0)>0?'text-success-600':'text-surface-700'">{{ ((bet.best_edge||0)*100).toFixed(1) }}%</p>
            <p class="text-[11px] text-surface-400">Edge</p>
          </div>
        </div>
        <div class="mt-3 grid grid-cols-4 gap-3 border-t border-surface-100 pt-3">
          <div class="text-center"><p class="text-xs font-semibold text-surface-700">{{ ((bet.best_ev||0)*100).toFixed(1) }}%</p><p class="text-[10px] text-surface-400">EV</p></div>
          <div class="text-center"><p class="text-xs font-semibold text-surface-700">{{ ((bet.best_kelly||0)*100).toFixed(1) }}%</p><p class="text-[10px] text-surface-400">Kelly</p></div>
          <div class="text-center"><p class="text-xs font-semibold" :class="(bet.value_score||0)>=70?'text-success-600':'text-surface-700'">{{ bet.value_score || 0 }}</p><p class="text-[10px] text-surface-400">价值分</p></div>
          <div class="text-center"><p class="text-xs font-semibold" :class="(bet.market_prob||0)>=0.5?'text-surface-700':'text-surface-700'">{{ ((bet.market_prob||0)*100).toFixed(0) }}%</p><p class="text-[10px] text-surface-400">市场概率</p></div>
        </div>
      </div>
    </div>
  </div>
</template>
