<script setup lang="ts">
defineProps<{ status: string }>()
const labels: Record<string, string> = {
  draft: 'Скоро начнём',
  active: 'Игра идёт',
  finished: 'Игра завершена',
  cancelled: 'Отменена',
}
</script>
<template>
  <span class="status" :class="status"><i></i>{{ labels[status] || status }}</span>
</template>
