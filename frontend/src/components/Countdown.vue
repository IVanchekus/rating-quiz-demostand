<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
const props = defineProps<{ endsAt: string | null; serverTime: string; status: string }>()
const now = ref(Date.now())
const offset = ref(0)
watch(() => props.serverTime, value => { offset.value = Date.parse(value) - Date.now() }, { immediate: true })
const timer = setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => clearInterval(timer))
const remaining = computed(() => {
  if (props.status === 'finished') return '00:00'
  if (!props.endsAt) return '— : —'
  const seconds = Math.max(0, Math.ceil((Date.parse(props.endsAt) - now.value - offset.value) / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
})
</script>
<template><span class="countdown">{{ remaining }}</span></template>
