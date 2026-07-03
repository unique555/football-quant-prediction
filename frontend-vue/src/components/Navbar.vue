<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
const navItems = [
  { path: '/', label: '控制台', icon: '◉' },
  { path: '/value', label: '价值投注', icon: '◆' },
  { path: '/today', label: '今日', icon: '▣' },
  { path: '/predict', label: '预测', icon: '⌕' },
  { path: '/stats', label: '统计', icon: '⬆' },
  { path: '/system', label: '系统', icon: '⚙' },
]
</script>
<template>
  <header class="sticky top-0 z-50 border-b border-surface-200 bg-white/90 backdrop-blur-lg">
    <div class="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
      <router-link to="/" class="flex items-center gap-2.5">
        <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-indigo-700 text-white text-sm font-bold shadow-sm">Q</span>
        <span class="text-sm font-bold tracking-tight text-surface-900">QuantPredict</span>
      </router-link>
      <nav class="flex items-center gap-0.5">
        <router-link v-for="item in navItems" :key="item.path" :to="item.path"
          class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150"
          :class="route.path === item.path || (item.path !== '/' && route.path.startsWith(item.path))
            ? 'bg-indigo-50 text-indigo-700 shadow-sm'
            : 'text-surface-500 hover:bg-surface-50 hover:text-surface-700'">
          <span class="text-[10px]">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
    </div>
  </header>
</template>
