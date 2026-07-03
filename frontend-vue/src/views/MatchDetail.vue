<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getMatchDetail } from '@/api/client'

const route = useRoute()
const detail = ref<any>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    detail.value = await getMatchDetail(route.params.id as string)
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

const fmtDate = (d: string | null) => d ? d.slice(0, 16).replace('T', ' ') : '-'
const riskClass = (r: string | null) => r === '低' ? 'bg-green-50 text-green-700' : r === '高' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'
</script>

<template>
  <div>
    <router-link to="/" class="inline-flex items-center gap-1 text-sm text-sky-700 hover:text-sky-900 mb-4">← 返回控制台</router-link>

    <div v-if="loading" class="py-20 text-center text-slate-500">加载中...</div>
    <div v-else-if="error" class="py-20 text-center text-red-500">{{ error }}</div>
    <div v-else-if="detail">
      <!-- 比赛标题 -->
      <div class="rounded-lg border border-slate-200 bg-white p-6">
        <div class="flex items-center gap-2 text-sm text-slate-500">
          <span class="rounded bg-slate-100 px-2 py-0.5">{{ detail.league }}</span>
          <span>{{ fmtDate(detail.kickoff) }}</span>
        </div>
        <h1 class="mt-2 text-2xl font-bold text-slate-950">{{ detail.home_team }} <span class="text-slate-400">vs</span> {{ detail.away_team }}</h1>
        <div v-if="detail.result?.home_goals !== null" class="mt-2">
          <span class="text-lg font-bold">结果: {{ detail.result.home_goals }} - {{ detail.result.away_goals }}</span>
        </div>
      </div>

      <!-- 预测列表 -->
      <div v-for="pred in (detail.predictions || [])" :key="pred.id || pred.fixture_id" class="mt-4 rounded-lg border border-slate-200 bg-white overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 class="font-semibold">🎯 预测</h2>
          <span class="text-xs text-slate-500">{{ fmtDate(pred.created_at) }}</span>
        </div>
        <div class="grid grid-cols-2 gap-4 p-5">
          <div><p class="text-xs text-slate-500">推荐方向</p><p class="font-semibold">{{ pred.best_pick || '观望' }}</p></div>
          <div><p class="text-xs text-slate-500">风险</p><span class="rounded px-2 py-0.5 text-xs font-medium" :class="riskClass(pred.risk)">{{ pred.risk || '中' }}</span></div>
          <div><p class="text-xs text-slate-500">价值评分</p><p class="font-semibold">{{ pred.value_score ?? 0 }}/100</p></div>
          <div><p class="text-xs text-slate-500">复盘状态</p><p class="font-semibold">{{ pred.settled_status || 'pending' }}</p></div>
        </div>
        <!-- 分析报告 -->
        <details v-if="pred.report_text" class="border-t border-slate-100">
          <summary class="cursor-pointer px-5 py-3 text-sm font-medium text-sky-700 hover:text-sky-900">📊 查看完整分析报告</summary>
          <pre class="max-h-[500px] overflow-y-auto whitespace-pre-wrap break-words bg-slate-50 p-4 text-xs">{{ pred.report_text.slice(0, 10000) }}</pre>
        </details>
      </div>

      <!-- 价值候选 -->
      <div v-if="detail.value_candidates?.length" class="mt-4 rounded-lg border border-slate-200 bg-white overflow-hidden">
        <div class="border-b border-slate-100 px-5 py-3"><h2 class="font-semibold">💰 价值候选</h2></div>
        <div class="divide-y divide-slate-100">
          <div v-for="c in detail.value_candidates" :key="c.market + c.pick" class="flex items-center justify-between px-5 py-3 text-sm">
            <div><span class="font-medium">{{ c.market }}</span> · {{ c.display_pick || c.pick }} @ {{ c.odds }}<span v-if="c.best_bookmaker" class="ml-1 text-xs text-slate-500">({{ c.best_bookmaker }})</span></div>
            <div class="text-right">
              <p :class="(c.edge || 0) >= 0 ? 'text-green-600' : 'text-red-600'">Edge: {{ ((c.edge || 0) * 100).toFixed(1) }}%</p>
              <p class="text-xs text-slate-500">EV: {{ ((c.ev || 0) * 100).toFixed(1) }}%</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 赔率快照 -->
      <div v-if="detail.odds_snapshots?.length" class="mt-4 rounded-lg border border-slate-200 bg-white overflow-hidden">
        <div class="border-b border-slate-100 px-5 py-3"><h2 class="font-semibold">📈 赔率快照</h2></div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <thead class="bg-slate-50 text-left text-xs text-slate-500"><tr><th class="px-4 py-3">类型</th><th class="px-4 py-3">庄家</th><th class="px-4 py-3">主胜</th><th class="px-4 py-3">平局</th><th class="px-4 py-3">客胜</th></tr></thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="s in detail.odds_snapshots" :key="s.captured_at + s.bookmaker" class="hover:bg-slate-50">
                <td class="px-4 py-3 text-xs">{{ s.snapshot_type }}</td>
                <td class="px-4 py-3">{{ s.bookmaker }}</td>
                <td class="px-4 py-3">{{ s.home_odds ?? '-' }}</td>
                <td class="px-4 py-3">{{ s.draw_odds ?? '-' }}</td>
                <td class="px-4 py-3">{{ s.away_odds ?? '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
