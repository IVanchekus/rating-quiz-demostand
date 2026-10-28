<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Users } from '@lucide/vue'
import type { Player } from '../services/api'

const props = defineProps<{
  players: Player[]
  count: number
  search: string
  hasLeaders?: boolean
}>()
const emit = defineEmits<{
  pageStatus: [status: { pageIndex: number; pageCount: number; secondsUntilNextPage: number }]
}>()

const tableViewport = ref<HTMLElement | null>(null)
const rowsPerPage = ref(4)
const displayRowHeight = ref(0)
const pageIndex = ref(0)
const secondsUntilNextPage = ref(0)
const pageDurationMs = 12000

let resizeObserver: ResizeObserver | undefined
let pageTimer = 0
let countdownTimer = 0

const pageCount = computed(() => Math.max(1, Math.ceil(props.players.length / rowsPerPage.value)))
const visiblePlayers = computed(() =>
  props.players.slice(
    pageIndex.value * rowsPerPage.value,
    (pageIndex.value + 1) * rowsPerPage.value,
  ),
)

function schedulePageChange() {
  window.clearTimeout(pageTimer)
  window.clearInterval(countdownTimer)
  pageTimer = 0
  countdownTimer = 0
  secondsUntilNextPage.value = 0
  if (pageCount.value < 2) return

  const deadline = Date.now() + pageDurationMs
  secondsUntilNextPage.value = Math.ceil(pageDurationMs / 1000)
  countdownTimer = window.setInterval(() => {
    secondsUntilNextPage.value = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
  }, 250)
  pageTimer = window.setTimeout(() => {
    pageIndex.value = (pageIndex.value + 1) % pageCount.value
  }, pageDurationMs)
}

function measureRowsPerPage() {
  const viewport = tableViewport.value
  if (!viewport || !props.players.length) {
    window.clearTimeout(pageTimer)
    window.clearInterval(countdownTimer)
    pageTimer = 0
    countdownTimer = 0
    secondsUntilNextPage.value = 0
    return
  }
  resizeObserver?.observe(viewport)

  const header = viewport.querySelector('thead')
  const row = viewport.querySelector('tbody tr') as HTMLTableRowElement | null
  if (!header || !row) return

  const availableHeight = viewport.clientHeight - header.getBoundingClientRect().height
  const assignedHeight = row.style.height
  row.style.height = 'auto'
  const rowHeight = row.getBoundingClientRect().height
  row.style.height = assignedHeight
  if (!rowHeight) return

  const nextRowsPerPage = Math.max(1, Math.floor(availableHeight / rowHeight))
  if (rowsPerPage.value !== nextRowsPerPage) {
    rowsPerPage.value = nextRowsPerPage
    pageIndex.value = 0
  } else if (pageIndex.value >= pageCount.value) {
    pageIndex.value = 0
  }
  const rowsOnPage = Math.min(
    rowsPerPage.value,
    props.players.length - pageIndex.value * rowsPerPage.value,
  )
  displayRowHeight.value = availableHeight / Math.max(1, rowsOnPage)
  schedulePageChange()
}

onMounted(() => {
  resizeObserver = new ResizeObserver(measureRowsPerPage)
  if (tableViewport.value) resizeObserver.observe(tableViewport.value)
  nextTick(measureRowsPerPage)
})

watch(
  () => props.players.map((player) => player.participant_id).join(','),
  () => {
    pageIndex.value = 0
    nextTick(measureRowsPerPage)
  },
)

watch(pageIndex, () => {
  nextTick(() => {
    measureRowsPerPage()
  })
})

watch(
  [pageIndex, pageCount, secondsUntilNextPage],
  ([currentPage, totalPages, seconds]) => {
    emit('pageStatus', {
      pageIndex: currentPage + 1,
      pageCount: totalPages,
      secondsUntilNextPage: seconds,
    })
  },
  { immediate: true },
)

onUnmounted(() => {
  window.clearTimeout(pageTimer)
  window.clearInterval(countdownTimer)
  resizeObserver?.disconnect()
})
</script>
<template>
  <div v-if="!players.length" class="empty-state">
    <Users :size="36" :stroke-width="1.3" />
    <h3>
      {{
        search
          ? 'Участник не найден'
          : hasLeaders
            ? 'Других участников пока нет'
            : 'Первое место пока свободно'
      }}
    </h3>
    <p>
      {{
        search
          ? 'Попробуйте другое имя или никнейм.'
          : hasLeaders
            ? 'Остальные участники появятся здесь.'
            : 'Сканируйте QR-код, отвечайте на вопросы и станьте первым в рейтинге.'
      }}
    </p>
  </div>
  <div v-else ref="tableViewport" class="table-scroll">
    <table class="leaderboard-table">
      <thead>
        <tr>
          <th>Место</th>
          <th>Участник</th>
          <th>Прогресс</th>
          <th class="right">Баллы</th>
        </tr>
      </thead>
      <Transition name="table-page-fade" mode="out-in">
        <tbody :key="pageIndex">
          <tr
            v-for="player in visiblePlayers"
            :key="player.participant_id"
            :style="{ height: `${displayRowHeight}px` }"
          >
            <td>
              <span class="place">{{ player.completed ? player.place : '—' }}</span>
            </td>
            <td>
              <span class="player-name">{{ player.display_name }}</span>
            </td>
            <td>
              <div class="progress-cell">
                <div class="progress-track">
                  <i
                    :style="{ width: `${Math.min(100, (player.closed_questions / count) * 100)}%` }"
                  ></i>
                </div>
                <span
                  >{{ player.closed_questions }}<span class="muted"> / {{ count }}</span></span
                >
              </div>
            </td>
            <td class="right">
              <template v-if="player.completed && player.total_score !== null"
                ><strong class="score-number">{{
                  player.total_score.toLocaleString('ru-RU')
                }}</strong
                ><span class="score-unit"> б.</span></template
              ><span v-else class="pending-score">{{
                player.status === 'expired' ? 'Не завершён' : 'В игре'
              }}</span>
            </td>
          </tr>
        </tbody>
      </Transition>
    </table>
  </div>
</template>
