<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getValueToday, getStats, getTodayMatches, getRecentPredictions } from '@/api/client'

const stats = ref<any>({})
const valueBets = ref<any[]>([])
const todayMatches = ref<any[]>([])
const predictions = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const [s, v, t, p] = await Promise.all([
      getStats(), getValueToday(5), getTodayMatches(), getRecentPredictions(12),
    ])
    stats.value = s; valueBets.value = v; todayMatches.value = t; predictions.value = p
  } catch (e) { console.error(e) }
  finally { loading.value = false }
})
const analyzedToday = computed(() => todayMatches.value.filter((m: any) => m.analyzed).length)
const fmt = (d: string | null) => d ? d.slice(0, 16).replace('T', ' ') : '-'
</script>
<template>
  <div>
    <div class="mb-6 flex items-end justify-between border-b border-slate-200 pb-5">
      <div><h1 class="text-2xl font-semibold text-slate-950">控制台</h1><p class="mt-1 text-sm text-slate-600">API-Football 赔率、引擎判断、价值候选和复盘结果</p></div>
      <router-link to="/predict" class="rounded-md bg-slate-950 px-3 py-2 text-sm text-white hover:bg-slate-800">单场预测</router-link>
    </div>
    <div v-if="!loading" class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <div class="rounded-lg border border-slate-200 bg-white p-4"><p class="text-sm text-slate-500">今日比赛</p><p class="mt-3 text-2xl font-semibold">{{ todayMatches.length }}</p><p class="mt-1 text-xs text-slate-500">{{ analyzedToday }} 场已分析</p></div>
      <div class="rounded-lg border border-slate-200 bg-white p-4"><p class="text-sm text-slate-500">总分析</p><p class="mt-3 text-2xl font-semibold">{{ stats.total_predictions || 0 }}</p><p class="mt-1 text-xs text-slate-500">{{ stats.value_predictions || 0 }} 条有价值方向</p></div>
      <div class="rounded-lg border border-slate-200 bg-white p-4"><p class="text-sm text-slate-500">价值方向占比</p><p class="mt-3 text-2xl font-semibold">{{ ((stats.recent_value_rate || 0) * 100).toFixed(1) }}%</p><p class="mt-1 text-xs text-slate-500">{{ stats.settled_predictions || 0 }} 条已复盘</p></div>
      <div class="rounded-lg border border-slate-200 bg-white p-4"><p class="text-sm text-slate-500">复盘收益</p><p class="mt-3 text-2xl font-semibold">{{ stats.total_profit || 0 }}u</p><p class="mt-1 text-xs text-slate-500">总盈亏</p></div>
    </div>
    <router-link to="/value" class="mt-4 flex items-center justify-between rounded-lg border border-amber-200 bg-gradient-to-r from-amber-50 to-yellow-50 p-4 hover:shadow-md">
      <div class="flex items-center gap-3"><span class="text-2xl">🏆</span><div><p class="font-semibold text-slate-950">价值投注看板</p><p class="text-xs text-slate-600">系统自动筛选 Edge &gt; 3% 的价值投注 + Kelly 注额建议</p></div></div>
      <span class="text-amber-600">→</span>
    </router-link>
    <div class="mt-6 grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
      <div class="rounded-lg border border-slate-200 bg-white overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-100 px-5 py-4"><h2 class="font-semibold">核心输出</h2><router-link to="/today" class="text-sm text-sky-700">今日比赛</router-link></div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <thead class="bg-slate-50 text-left text-xs text-slate-500 uppercase"><tr><th class="px-5 py-3">比赛</th><th class="px-5 py-3">方向</th><th class="px-5 py-3">赔率</th><th class="px-5 py-3">EV</th><th class="px-5 py-3">风险</th></tr></thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="item in valueBets" :key="item.fixture_id" class="hover:bg-slate-50">
                <td class="px-5 py-4"><router-link :to="'/matches/'+item.fixture_id" class="font-medium hover:text-sky-700">{{ item.home_team }} vs {{ item.away_team }}</router-link><div class="mt-1 text-xs text-slate-500">{{ item.league }} · {{ fmt(item.kickoff) }}</div></td>
                <td class="px-5 py-4">{{ item.best_pick || '观望' }}</td>
                <td class="px-5 py-4">{{ item.best_odds }}</td>
                <td class="px-5 py-4 text-emerald-700">{{ ((item.best_ev || 0) * 100).toFixed(1) }}%</td>
                <td class="px-5 py-4"><span class="rounded px-2 py-0.5 text-xs" :class="item.risk==='低'?'bg-green-50 text-green-700':item.risk==='高'?'bg-red-50 text-red-700':'bg-amber-50 text-amber-700'">{{ item.risk || '中' }}</span></td>
              </tr>
              <tr v-if="!valueBets.length"><td colspan="5" class="px-5 py-8 text-center text-slate-500">暂无价值输出</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="space-y-6">
        <div class="rounded-lg border border-slate-200 bg-white">
          <div class="flex items-center justify-between border-b border-slate-100 px-5 py-4"><h2 class="font-semibold">今日状态</h2><span class="text-xs text-slate-500">{{ todayMatches.length }} 场</span></div>
          <div class="divide-y divide-slate-100">
            <router-link v-for="m in todayMatches.slice(0,5)" :key="m.fixture_id" :to="'/matches/'+m.fixture_id" class="block px-5 py-3 hover:bg-slate-50">
              <div class="flex items-center justify-between text-sm"><span class="font-medium">{{ m.home_team }} vs {{ m.away_team }}</span><span class="text-xs" :class="m.analyzed?'text-green-600':'text-slate-400'">{{ m.analyzed?'已分析':'待分析' }}</span></div>
              <div class="mt-1 text-xs text-slate-500">{{ m.league || '-' }} · {{ fmt(m.kickoff) }}</div>
            </router-link>
            <div v-if="!todayMatches.length" class="px-5 py-6 text-sm text-slate-500 text-center">今日暂无入库比赛</div>
          </div>
        </div>
      </div>
    </div>
    <div class="mt-6 rounded-lg border border-slate-200 bg-white overflow-hidden">
      <div class="flex items-center justify-between border-b border-slate-100 px-5 py-4"><h2 class="font-semibold">最近预测</h2><span class="text-xs text-slate-500">{{ predictions.length }} 条</span></div>
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-200 text-sm">
          <thead class="bg-slate-50 text-left text-xs text-slate-500 uppercase"><tr><th class="px-5 py-3">比赛</th><th class="px-5 py-3">方向</th><th class="px-5 py-3">评分</th><th class="px-5 py-3">复盘</th></tr></thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="p in predictions" :key="p.id" class="hover:bg-slate-50">
              <td class="px-5 py-4"><router-link :to="'/matches/'+p.fixture_id" class="font-medium hover:text-sky-700">{{ p.home_team }} vs {{ p.away_team }}</router-link></td>
              <td class="px-5 py-4">{{ p.best_pick || '观望' }}</td>
              <td class="px-5 py-4">{{ p.value_score ?? 0 }}</td>
              <td class="px-5 py-4">{{ p.settled_status || 'pending' }}</td>
            </tr>
            <tr v-if="!predictions.length"><td colspan="4" class="px-5 py-8 text-center text-slate-500">暂无预测记录</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
