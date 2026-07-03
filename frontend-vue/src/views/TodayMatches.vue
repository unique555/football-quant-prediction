<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getTodayMatches } from '@/api/client'

const matches = ref<any[]>([])
onMounted(async () => {
  try { matches.value = await getTodayMatches() } catch (e) { console.error(e) }
})
const fmtDate = (d: string | null) => d ? d.slice(0, 16).replace('T', ' ') : '?'
</script>
<template>
  <div>
    <div class="mb-6 border-b border-slate-200 pb-5"><h1 class="text-2xl font-semibold text-slate-950">今日比赛</h1><p class="mt-1 text-sm text-slate-600">{{ matches.length }} 场已入库</p></div>
    <div class="space-y-2">
      <router-link v-for="m in matches" :key="m.fixture_id" :to="'/matches/'+m.fixture_id" class="block rounded-lg border border-slate-200 bg-white p-4 hover:shadow-md">
        <div class="flex items-center justify-between">
          <div><p class="font-semibold text-slate-950">{{ m.home_team }} vs {{ m.away_team }}</p><p class="text-sm text-slate-500">{{ m.league }} · {{ fmtDate(m.kickoff) }}</p></div>
          <div class="text-right"><span class="rounded px-2 py-0.5 text-xs" :class="m.analyzed?'bg-green-50 text-green-600':'bg-slate-100 text-slate-500'">{{ m.analyzed?'已分析':'待分析' }}</span><p v-if="m.score" class="mt-1 text-sm font-semibold">{{ m.score }}</p></div>
        </div>
      </router-link>
      <div v-if="!matches.length" class="py-20 text-center text-slate-400"><p class="text-lg">📅</p><p class="text-sm">今日暂无比赛</p></div>
    </div>
  </div>
</template>
