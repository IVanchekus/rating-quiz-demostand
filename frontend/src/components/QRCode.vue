<script setup lang="ts">
import { ref, watch } from 'vue'
import QRCode from 'qrcode'
const props = defineProps<{ value: string }>()
const url = ref('')
watch(() => props.value, async value => {
  url.value = await QRCode.toDataURL(value, { width: 240, margin: 1, color: { dark: '#173c37', light: '#ffffff' }, errorCorrectionLevel: 'M' })
}, { immediate: true })
</script>
<template><img v-if="url" :src="url" class="qr-code" alt="QR-код для входа в Telegram-игру" width="180" height="180" /></template>
