import { onUnmounted, ref, watch, type Ref } from 'vue'
import { api, type Leaderboard } from '../services/api'

export function useLeaderboardPolling(code: Ref<string>) {
  const data = ref<Leaderboard | null>(null)
  const error = ref('')
  const loading = ref(false)
  const updatedAt = ref<Date | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  let version = 0
  let running = false

  async function poll(generation: number) {
    if (!code.value || running) return
    running = true
    loading.value = !data.value
    const requestController = new AbortController()
    controller = requestController
    // Ensure a stalled network request eventually permits a retry.
    const timeout = setTimeout(() => requestController.abort(), 10000)
    try {
      const result = await api<Leaderboard>(
        `/rooms/${encodeURIComponent(code.value)}/leaderboard`,
        { signal: controller.signal },
      )
      if (generation !== version) return
      data.value = result
      updatedAt.value = new Date()
      error.value = ''
    } catch (e) {
      if (generation === version)
        error.value =
          e instanceof Error && e.name !== 'AbortError' ? e.message : 'Нет связи с сервером'
    } finally {
      clearTimeout(timeout)
      if (generation === version) {
        loading.value = false
        running = false
        if (data.value?.status !== 'finished' && data.value?.status !== 'cancelled') {
          timer = setTimeout(() => poll(generation), 15000)
        }
      }
    }
  }

  watch(
    code,
    () => {
      version++
      clearTimeout(timer)
      controller?.abort()
      running = false
      data.value = null
      error.value = ''
      void poll(version)
    },
    { immediate: true },
  )
  onUnmounted(() => {
    version++
    clearTimeout(timer)
    controller?.abort()
  })
  function refresh() {
    if (!running) {
      clearTimeout(timer)
      void poll(version)
    }
  }
  return { data, error, loading, updatedAt, refresh }
}
