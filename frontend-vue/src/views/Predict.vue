<script setup lang="ts">
import { ref } from 'vue'
import { predictMatch } from '@/api/client'
const query = ref('')
const result = ref<any>(null)
const loading = ref(false)
async function doPredict() {
  if (!query.value.trim()) return
  loading.value = true; result.value = null
  try { result.value = await predictMatch(query.value) }
  catch (e: any) { result.value = { status: 'error', message: e.message } }
  finally { loading.value = false }
}
</script>
<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-xl font-bold tracking-tight text-surface-900">单场预测</h1>
      <p class="mt-0.5 text-xs text-surface-500">手动输入比赛名称，调取完整分析管线</p>
    </div>
    <div class="rounded-xl border border-surface-100 bg-white p-5 shadow-card">
      <div class="flex gap-3">
        <input v-model="query" @keyup.enter="doPredict" placeholder="输入比赛，如：阿森纳 vs 切尔西" class="flex-1 rounded-lg border border-surface-200 px-4 py-2.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 transition-all" />
        <button @click="doPredict" :disabled="loading" class="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors">{{ loading?'分析中...':'开始分析' }}</button>
      </div>
    </div>
    <div v-if="result">
      <div v-if="result.status==='error'||result.status==='not_found'" class="rounded-xl border border-danger-200 bg-danger-50 p-4 text-sm text-danger-600">{{ result.message || '未找到比赛' }}</div>
      <div v-else class="rounded-xl border border-surface-100 bg-white shadow-card overflow-hidden">
        <div class="border-b border-surface-100 px-5 py-3">
          <h2 class="text-sm font-semibold text-surface-900">分析结果</h2>
        </div>
        <pre class="max-h-[600px] overflow-y-auto whitespace-pre-wrap break-words bg-surface-50/50 p-5 text-xs leading-relaxed text-surface-700">{{ result.message }}</pre>
      </div>
    </div>
  </div>
</template>
