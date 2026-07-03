<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getValueToday, getStats, getTodayMatches, getRecentPredictions } from '@/api/client'

const stats = ref<any>({})
const valueBets = ref<any[]>([])
const todayMatches = ref<any[]>([])
const predictions = ref<any[]>([])

onMounted(async () => {
  try {
    const [s, v, t, p] = await Promise.all([
      getStats(), getValueToday(5), getTodayMatches(), getRecentPredictions(12),
    ])
    stats.value = s; valueBets.value = v; todayMatches.value = t; predictions.value = p
  } catch (e) { console.error(e) }
})

const analyzedCount = computed(() => todayMatches.value.filter((m: any) => m.analyzed).length)
const fmt = (d: string | null) => d ? d.slice(0, 16).replace('T', ' ') : '-'
const riskClass = (r: string | null) => r === '低' ? 'bg-success-50 text-success-600' : r === '高' ? 'bg-danger-50 text-danger-600' : 'bg-warning-50 text-warning-600'
</script>
<template>
  <div class="space-y-5">
    <!-- 头部 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold tracking-tight text-surface-900">控制台</h1>
        <p class="mt-0.5 text-xs text-surface-500">QuantPredict 量化预测系统 · 实时监控面板</p>
      </div>
      <div class="flex items-center gap-2">
        <span class="flex items-center gap-1.5 rounded-full bg-success-50 px-3 py-1 text-xs font-medium text-success-600"><span class="h-1.5 w-1.5 rounded-full bg-success-400"></span>系统在线</span>
        <router-link to="/predict" class="rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 transition-colors">+ 新分析</router-link>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div class="rounded-xl border border-surface-100 bg-white p-4 shadow-card">
        <div class="flex items-center justify-between"><span class="text-xs font-medium text-surface-500">今日比赛</span><span class="text-lg">📅</span></div>
        <p class="mt-2 text-2xl font-bold text-surface-900">{{ todayMatches.length }}</p>
        <p class="mt-0.5 text-xs text-surface-400">{{ analyzedCount }} 场已生成分析</p>
      </div>
      <div class="rounded-xl border border-surface-100 bg-white p-4 shadow-card">
        <div class="flex items-center justify-between"><span class="text-xs font-medium text-surface-500">总分析量</span><span class="text-lg">📊</span></div>
        <p class="mt-2 text-2xl font-bold text-surface-900">{{ stats.total_predictions || 0 }}</p>
        <p class="mt-0.5 text-xs text-surface-400">{{ stats.value_predictions || 0 }} 条价值方向</p>
      </div>
      <div class="rounded-xl border border-surface-100 bg-white p-4 shadow-card">
        <div class="flex items-center justify-between"><span class="text-xs font-medium text-surface-500">价值占比</span><span class="text-lg">🎯</span></div>
        <p class="mt-2 text-2xl font-bold text-surface-900">{{ ((stats.recent_value_rate || 0) * 100).toFixed(1) }}%</p>
        <p class="mt-0.5 text-xs text-surface-400">{{ stats.settled_predictions || 0 }} 条已复盘</p>
      </div>
      <div class="rounded-xl border border-surface-100 bg-white p-4 shadow-card">
        <div class="flex items-center justify-between"><span class="text-xs font-medium text-surface-500">复盘收益</span><span class="text-lg">💰</span></div>
        <p class="mt-2 text-2xl font-bold" :class="(stats.total_profit||0)>=0?'text-success-600':'text-danger-600'">{{ (stats.total_profit || 0).toFixed(1) }}u</p>
        <p class="mt-0.5 text-xs text-surface-400">累计盈亏</p>
      </div>
    </div>

    <!-- 价值投注入口 -->
    <router-link to="/value" class="group flex items-center justify-between rounded-xl border border-amber-200/60 bg-gradient-to-r from-amber-50/80 to-orange-50/80 p-4 shadow-card hover:shadow-card-hover transition-all">
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-sm">🏆</div>
        <div><p class="text-sm font-semibold text-surface-900 group-hover:text-amber-700 transition-colors">价值投注看板</p><p class="mt-0.5 text-xs text-surface-500">Edge &gt; 3% 的价值投注 · 实时 Kelly 注额建议</p></div>
      </div>
      <span class="text-amber-500 group-hover:text-amber-600 transition-colors text-lg">→</span>
    </router-link>

    <!-- 核心区域 -->
    <div class="grid gap-5 xl:grid-cols-[1.35fr_0.85fr]">
      <!-- 核心输出 -->
      <div class="rounded-xl border border-surface-100 bg-white shadow-card overflow-hidden">
        <div class="flex items-center justify-between px-5 py-3.5 border-b border-surface-100">
          <h2 class="text-sm font-semibold text-surface-900">📋 核心输出</h2>
          <router-link to="/today" class="text-xs font-medium text-indigo-600 hover:text-indigo-700">查看全部 →</router-link>
        </div>
        <table class="w-full text-xs">
          <thead><tr class="border-b border-surface-50 bg-surface-50/50"><th class="px-5 py-2.5 text-left font-medium text-surface-500">比赛</th><th class="px-5 py-2.5 text-left font-medium text-surface-500">方向</th><th class="px-5 py-2.5 text-left font-medium text-surface-500">赔率</th><th class="px-5 py-2.5 text-left font-medium text-surface-500">EV</th><th class="px-5 py-2.5 text-left font-medium text-surface-500">风险</th></tr></thead>
          <tbody class="divide-y divide-surface-50">
            <tr v-for="item in valueBets" :key="item.fixture_id" class="hover:bg-surface-50/50 transition-colors">
              <td class="px-5 py-3"><router-link :to="'/matches/'+item.fixture_id" class="font-medium text-surface-900 hover:text-indigo-600">{{ item.home_team }} vs {{ item.away_team }}</router-link><div class="mt-0.5 text-surface-400">{{ item.league }}</div></td>
              <td class="px-5 py-3 text-surface-700">{{ item.best_pick || '观望' }}</td>
              <td class="px-5 py-3 font-medium">{{ item.best_odds }}</td>
              <td class="px-5 py-3 text-success-600 font-medium">{{ ((item.best_ev||0)*100).toFixed(1) }}%</td>
              <td class="px-5 py-3"><span class="rounded-md px-2 py-0.5 text-[11px] font-medium" :class="riskClass(item.risk)">{{ item.risk || '中' }}</span></td>
            </tr>
            <tr v-if="!valueBets.length"><td colspan="5" class="px-5 py-8 text-center text-surface-400">暂无价值输出</td></tr>
          </tbody>
        </table>
      </div>
      <!-- 今日状态 -->
      <div class="rounded-xl border border-surface-100 bg-white shadow-card overflow-hidden">
        <div class="flex items-center justify-between px-5 py-3.5 border-b border-surface-100">
          <h2 class="text-sm font-semibold text-surface-900">📌 今日动态</h2>
          <span class="text-xs text-surface-400">{{ todayMatches.length }} 场</span>
        </div>
        <div class="divide-y divide-surface-50">
          <router-link v-for="m in todayMatches.slice(0,6)" :key="m.fixture_id" :to="'/matches/'+m.fixture_id" class="flex items-center justify-between px-5 py-3 hover:bg-surface-50/50 transition-colors">
            <div class="min-w-0"><p class="text-xs font-medium text-surface-900 truncate">{{ m.home_team }} vs {{ m.away_team }}</p><p class="mt-0.5 text-[11px] text-surface-400">{{ m.league }}</p></div>
            <span class="shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium" :class="m.analyzed?'bg-success-50 text-success-600':'bg-surface-100 text-surface-500'">{{ m.analyzed?'已分析':'待分析' }}</span>
          </router-link>
          <div v-if="!todayMatches.length" class="px-5 py-8 text-center text-xs text-surface-400">今日暂无比赛</div>
        </div>
      </div>
    </div>

    <!-- 最近预测 -->
    <div class="rounded-xl border border-surface-100 bg-white shadow-card overflow-hidden">
      <div class="flex items-center justify-between px-5 py-3.5 border-b border-surface-100">
        <h2 class="text-sm font-semibold text-surface-900">📄 最近预测</h2>
        <span class="text-xs text-surface-400">{{ predictions.length }} 条</span>
      </div>
      <table class="w-full text-xs">
        <thead><tr class="border-b border-surface-50 bg-surface-50/50"><th class="px-5 py-2.5 text-left font-medium text-surface-500">比赛</th><th class="px-5 py-2.5 text-left font-medium text-surface-500">方向</th><th class="px-5 py-2.5 text-left font-medium text-surface-500">评分</th><th class="px-5 py-2.5 text-left font-medium text-surface-500">复盘</th></tr></thead>
        <tbody class="divide-y divide-surface-50">
          <tr v-for="p in predictions" :key="p.id" class="hover:bg-surface-50/50 transition-colors">
            <td class="px-5 py-3"><router-link :to="'/matches/'+p.fixture_id" class="font-medium text-surface-900 hover:text-indigo-600">{{ p.home_team }} vs {{ p.away_team }}</router-link></td>
            <td class="px-5 py-3 text-surface-700">{{ p.best_pick || '观望' }}</td>
            <td class="px-5 py-3"><span class="rounded-md px-2 py-0.5 text-[11px] font-medium" :class="(p.value_score||0)>=70?'bg-success-50 text-success-600':(p.value_score||0)>=40?'bg-warning-50 text-warning-600':'bg-surface-100 text-surface-500'">{{ p.value_score||0 }}</span></td>
            <td class="px-5 py-3"><span class="rounded-md px-2 py-0.5 text-[11px] font-medium" :class="p.settled_status==='win'?'bg-success-50 text-success-600':p.settled_status==='loss'?'bg-danger-50 text-danger-600':'bg-surface-100 text-surface-500'">{{ p.settled_status||'pending' }}</span></td>
          </tr>
          <tr v-if="!predictions.length"><td colspan="4" class="px-5 py-8 text-center text-surface-400">暂无预测记录</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
