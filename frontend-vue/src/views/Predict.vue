<script setup lang="ts">
import { ref } from 'vue'
import { predictMatch } from '@/api/client'

const query = ref('')
const result = ref<any>(null)
const loading = ref(false)
const error = ref('')

async function doPredict() {
  if (!query.value.trim()) return
  loading.value = true; error.value = ''; result.value = null
  try {
    result.value = await predictMatch(query.value)
    if (result.value.status === 'not_found') error.value = '未找到比赛'
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}
</script>
<template>
  <div>
    <div class="mb-6 border-b border-slate-200 pb-5"><h1 class="text-2xl font-semibold text-slate-950">单场预测</h1><p class="mt-1 text-sm text-slate-600">手动输入比赛名称进行分析</p></div>
    <div class="rounded-lg border border-slate-200 bg-white p-6">
      <input v-model="query" @keyup.enter="doPredict" placeholder="输入比赛，如：阿森纳 vs 切尔西" class="w-full rounded-md border border-slate-300 px-4 py-2 text-sm focus:border-sky-500 focus:outline-none" />
      <button @click="doPredict" :disabled="loading" class="mt-3 rounded-md bg-slate-950 px-4 py-2 text-sm text-white hover:bg-slate-800 disabled:opacity-50">{{ loading ? '分析中...' : '开始分析' }}</button>
      <p v-if="error" class="mt-3 text-sm text-red-600">{{ error }}</p>
      <pre v-if="result?.message" class="mt-4 max-h-[500px] overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-xs">{{ result.message }}</pre>
    </div>
  </div>
</template>
