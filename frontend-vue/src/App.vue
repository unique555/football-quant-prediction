<script setup lang="ts">
import { RouterView } from 'vue-router'
import Navbar from './components/Navbar.vue'
</script>

<template>
  <div class="flex min-h-screen flex-col bg-slate-50">
    <Navbar />
    <main class="flex-1 mx-auto w-full max-w-7xl px-4 py-6">
      <RouterView />
    </main>
  </div>
</template>
