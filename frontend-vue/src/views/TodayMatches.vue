<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getTodayMatches } from '@/api/client'
const matches = ref<any[]>([])
onMounted(async () => {
  try { matches.value = await getTodayMatches() } catch (e) { console.error(e) }
})
const fmtDate = (d: string|null) => d ? d.slice(0,16).replace('T',' ') : '?'
</script>
<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold tracking-tight text-surface-900">今日比赛</h1>
        <p class="mt-0.5 text-xs text-surface-500">{{ matches.length }} 场已入库</p>
      </div>
      <span class="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">{{ matches.length }} 场</span>
    </div>
    <div v-if="!matches.length" class="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-surface-200 bg-white py-16 text-surface-400">
      <span class="mb-2 text-3xl">📅</span>
      <p class="text-sm font-medium">今日暂无比赛</p>
    </div>
    <div v-else class="grid gap-2">
      <router-link v-for="m in matches" :key="m.fixture_id" :to="'/matches/'+m.fixture_id" class="flex items-center justify-between rounded-xl border border-surface-100 bg-white p-4 shadow-card hover:shadow-card-hover transition-all">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 text-[11px] text-surface-500">
            <span class="rounded-md bg-surface-100 px-2 py-0.5 font-medium">{{ m.league || '?' }}</span>
            <span>{{ fmtDate(m.kickoff) }}</span>
          </div>
          <p class="mt-1 text-sm font-semibold text-surface-900">{{ m.home_team }} <span class="text-surface-300">vs</span> {{ m.away_team }}</p>
        </div>
        <div class="flex shrink-0 items-center gap-3">
          <span class="rounded-md px-2.5 py-1 text-xs font-medium" :class="m.analyzed?'bg-success-50 text-success-600':'bg-surface-100 text-surface-500'">{{ m.analyzed?'已分析':'待分析' }}</span>
          <span v-if="m.score" class="text-sm font-bold text-surface-700">{{ m.score }}</span>
          <span class="text-surface-300">→</span>
        </div>
      </router-link>
    </div>
  </div>
</template>
