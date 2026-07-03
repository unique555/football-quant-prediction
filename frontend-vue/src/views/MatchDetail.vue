<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getMatchDetail } from '@/api/client'

const route = useRoute()
const detail = ref<any>(null)
const loading = ref(true)

onMounted(async () => {
  try { detail.value = await getMatchDetail(route.params.id as string) } catch (e) { console.error(e) }
  finally { loading.value = false }
})

const fmtDate = (d: string | null) => d ? d.slice(0, 16).replace('T', ' ') : '-'
const riskClass = (r: string | null) => r === '低' ? 'bg-success-50 text-success-600' : r === '高' ? 'bg-danger-50 text-danger-600' : 'bg-warning-50 text-warning-600'
const resultClass = (s: string | null) => s === 'win' ? 'bg-success-50 text-success-600' : s === 'loss' ? 'bg-danger-50 text-danger-600' : 'bg-surface-100 text-surface-500'
</script>
<template>
  <div class="space-y-5">
    <router-link to="/" class="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700 transition-colors">← 返回控制台</router-link>
    <div v-if="loading" class="flex items-center justify-center py-20 text-surface-400 text-sm">加载中...</div>
    <template v-else-if="detail">
      <!-- 比赛标题卡片 -->
      <div class="rounded-xl border border-surface-100 bg-gradient-to-br from-white to-indigo-50/30 p-5 shadow-card">
        <div class="flex items-center gap-2 text-[11px] text-surface-500">
          <span class="rounded-md bg-indigo-50 px-2 py-0.5 font-medium text-indigo-700">{{ detail.league }}</span>
          <span>{{ fmtDate(detail.kickoff) }}</span>
        </div>
        <h1 class="mt-2 text-xl font-bold text-surface-900">{{ detail.home_team }} <span class="text-surface-300 mx-1">vs</span> {{ detail.away_team }}</h1>
        <div v-if="detail.result?.home_goals !== null" class="mt-3 inline-flex items-center gap-2 rounded-lg bg-surface-900 px-4 py-2"><span class="text-lg font-bold text-white">{{ detail.result.home_goals }}</span><span class="text-surface-400">:</span><span class="text-lg font-bold text-white">{{ detail.result.away_goals }}</span><span class="ml-2 text-[11px] text-surface-400">已结束</span></div>
      </div>

      <!-- 预测卡片 -->
      <div v-for="pred in (detail.predictions||[])" :key="pred.id" class="rounded-xl border border-surface-100 bg-white shadow-card overflow-hidden">
        <div class="flex items-center justify-between px-5 py-3 border-b border-surface-100 bg-surface-50/30">
          <h2 class="text-sm font-semibold text-surface-900">🎯 预测分析</h2>
          <span class="text-[11px] text-surface-400">{{ fmtDate(pred.created_at) }}</span>
        </div>
        <div class="grid grid-cols-2 gap-4 p-5">
          <div><p class="text-[11px] text-surface-500">推荐方向</p><p class="mt-0.5 text-sm font-semibold text-surface-900">{{ pred.best_display_pick || pred.best_pick || '观望' }}</p></div>
          <div><p class="text-[11px] text-surface-500">风险等级</p><span class="mt-0.5 inline-block rounded-md px-2 py-0.5 text-xs font-medium" :class="riskClass(pred.risk)">{{ pred.risk || '中' }}</span></div>
          <div><p class="text-[11px] text-surface-500">价值评分</p><p class="mt-0.5 text-sm font-semibold" :class="(pred.value_score||0)>=70?'text-success-600':'text-surface-900'">{{ pred.value_score || 0 }}/100</p></div>
          <div><p class="text-[11px] text-surface-500">复盘状态</p><span class="mt-0.5 inline-block rounded-md px-2 py-0.5 text-xs font-medium" :class="resultClass(pred.settled_status)">{{ pred.settled_status || 'pending' }}</span></div>
        </div>
        <details v-if="pred.report_text" class="border-t border-surface-100">
          <summary class="flex cursor-pointer items-center gap-2 px-5 py-3 text-xs font-medium text-indigo-600 hover:text-indigo-700 hover:bg-surface-50/50 transition-colors"><span>📊</span> 查看完整分析报告</summary>
          <pre class="max-h-[500px] overflow-y-auto whitespace-pre-wrap break-words bg-surface-50/50 p-5 text-xs leading-relaxed text-surface-700">{{ pred.report_text.slice(0,10000) }}</pre>
        </details>
      </div>

      <!-- 价值候选 -->
      <div v-if="detail.value_candidates?.length" class="rounded-xl border border-surface-100 bg-white shadow-card overflow-hidden">
        <div class="px-5 py-3 border-b border-surface-100"><h2 class="text-sm font-semibold text-surface-900">💰 价值候选</h2></div>
        <div class="divide-y divide-surface-50">
          <div v-for="c in detail.value_candidates" :key="c.market+c.pick" class="flex items-center justify-between px-5 py-3 hover:bg-surface-50/50 transition-colors">
            <div class="flex items-center gap-2"><span class="rounded-md bg-surface-100 px-2 py-0.5 text-[11px] font-medium text-surface-600">{{ c.market }}</span><span class="text-sm font-medium text-surface-900">{{ c.display_pick || c.pick }}</span><span class="text-xs text-surface-400">@ {{ c.odds }}</span></div>
            <div class="flex items-center gap-4 text-xs"><span :class="(c.edge||0)>=0?'text-success-600':'text-danger-600'" class="font-medium">Edge {{ ((c.edge||0)*100).toFixed(1) }}%</span><span class="text-surface-400">EV {{ ((c.ev||0)*100).toFixed(1) }}%</span></div>
          </div>
        </div>
      </div>

      <!-- 赔率快照 -->
      <div v-if="detail.odds_snapshots?.length" class="rounded-xl border border-surface-100 bg-white shadow-card overflow-hidden">
        <div class="px-5 py-3 border-b border-surface-100"><h2 class="text-sm font-semibold text-surface-900">📈 赔率快照</h2></div>
        <div class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead><tr class="border-b border-surface-50 bg-surface-50/50"><th class="px-4 py-2.5 text-left font-medium text-surface-500">类型</th><th class="px-4 py-2.5 text-left font-medium text-surface-500">庄家</th><th class="px-4 py-2.5 text-left font-medium text-surface-500">主胜</th><th class="px-4 py-2.5 text-left font-medium text-surface-500">平</th><th class="px-4 py-2.5 text-left font-medium text-surface-500">客胜</th></tr></thead>
            <tbody class="divide-y divide-surface-50">
              <tr v-for="s in detail.odds_snapshots" :key="s.captured_at+s.bookmaker" class="hover:bg-surface-50/50"><td class="px-4 py-2.5 text-surface-500">{{ s.snapshot_type }}</td><td class="px-4 py-2.5 font-medium">{{ s.bookmaker }}</td><td class="px-4 py-2.5">{{ s.home_odds ?? '-' }}</td><td class="px-4 py-2.5">{{ s.draw_odds ?? '-' }}</td><td class="px-4 py-2.5">{{ s.away_odds ?? '-' }}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
