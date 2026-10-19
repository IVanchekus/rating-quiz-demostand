<script setup lang="ts">
import { ArrowUpRight, ChartNoAxesCombined, ShieldCheck } from '@lucide/vue'
</script>
<template>
  <header class="site-header">
    <div class="header-inner">
      <RouterLink to="/" class="brand" aria-label="Питерский мостик, главная">
        <svg class="brand-symbol" viewBox="0 0 48 48" aria-hidden="true"><rect width="48" height="48" rx="13" fill="currentColor"/><path d="M10 33V17m28 16V17M10 20q14 22 28 0M10 33h28M18 28v5m12-5v5" stroke="#c4f1b0" stroke-width="2.5" fill="none"/></svg>
        <span>питерский мостик<small>ОБЪЕДИНЯЕМ ТЕХНОЛОГИИ И ЛЮДЕЙ</small></span>
      </RouterLink>
      <nav aria-label="Основная навигация">
        <RouterLink to="/" :class="{ current: $route.path !== '/admin' }"><ChartNoAxesCombined :size="17" />Рейтинг</RouterLink>
        <RouterLink to="/admin" :class="{ current: $route.path === '/admin' }"><ShieldCheck :size="17" />Организатору</RouterLink>
      </nav>
      <span class="header-label">IT CHALLENGE <ArrowUpRight :size="15" /></span>
    </div>
  </header>
  <main><RouterView /></main>
  <footer class="site-footer"><span>© {{ new Date().getFullYear() }} Питерский мостик</span><span>Связьком <i>·</i> Sensory Hub <i>·</i> Систематикс <i>·</i> Galaxy</span><span class="footer-note">Технологии начинаются с любопытства.</span></footer>
</template>
