<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
const navItems = [
  { path: '/', label: '控制台', icon: '📊' },
  { path: '/value', label: '价值投注', icon: '🏆' },
  { path: '/today', label: '今日', icon: '📅' },
  { path: '/predict', label: '预测', icon: '🔍' },
  { path: '/stats', label: '统计', icon: '📈' },
  { path: '/system', label: '系统', icon: '⚙️' },
]
const isActive = (p: string) => route.path === p || (p !== '/' && route.path.startsWith(p))
</script>
<template>
  <header class="sticky top-0 z-50 border-b border-slate-200 bg-white/95 backdrop-blur">
    <div class="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
      <router-link to="/" class="flex items-center gap-2 text-lg font-semibold text-slate-950">
        <span class="inline-flex h-9 w-9 items-center justify-center rounded-md bg-slate-950 text-white">⚽</span>
        FootballQuant
      </router-link>
      <nav class="flex items-center gap-1 overflow-x-auto">
        <router-link v-for="item in navItems" :key="item.path" :to="item.path"
          class="flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors"
          :class="isActive(item.path) ? 'bg-sky-50 text-sky-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'">
          <span>{{ item.icon }}</span>{{ item.label }}
        </router-link>
      </nav>
    </div>
  </header>
</template>
