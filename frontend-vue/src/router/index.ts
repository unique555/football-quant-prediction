import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
  { path: '/value', name: 'Value', component: () => import('@/views/ValueBets.vue') },
  { path: '/today', name: 'Today', component: () => import('@/views/TodayMatches.vue') },
  { path: '/predict', name: 'Predict', component: () => import('@/views/Predict.vue') },
  { path: '/stats', name: 'Stats', component: () => import('@/views/Stats.vue') },
  { path: '/system', name: 'System', component: () => import('@/views/System.vue') },
  { path: '/matches/:id', name: 'MatchDetail', component: () => import('@/views/MatchDetail.vue') },
]

export default createRouter({ history: createWebHistory(), routes })
