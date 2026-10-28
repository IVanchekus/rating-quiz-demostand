<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, Clock3, Radio, RefreshCw, Search, Sparkles, Trophy, Users } from '@lucide/vue'
import { api, type Room } from '../services/api'
import { splitLeaderboard } from '../services/leaderboard'
import { useLeaderboardPolling } from '../composables/useLeaderboardPolling'
import LeaderboardTable from '../components/LeaderboardTable.vue'
import QRCode from '../components/QRCode.vue'
import Countdown from '../components/Countdown.vue'
import RoomStatus from '../components/RoomStatus.vue'

const route = useRoute(),
  router = useRouter()
const rooms = ref<Room[]>([])
const roomError = ref('')
const searching = ref('')
const tablePageStatus = ref({ pageIndex: 1, pageCount: 1, secondsUntilNextPage: 0 })
const code = computed(() => String(route.params.code || ''))
const { data, error, loading, refresh } = useLeaderboardPolling(code)
const groups = computed(() => splitLeaderboard(data.value?.leaderboard || []))
const filtered = computed(() =>
  groups.value.table.filter((p) =>
    p.display_name.toLocaleLowerCase().includes(searching.value.toLocaleLowerCase()),
  ),
)
const finishedCount = computed(() => data.value?.leaderboard.filter((p) => p.completed).length || 0)
const topThree = computed(() => groups.value.podium)
let roomTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false

async function loadRooms() {
  try {
    rooms.value = await api<Room[]>('/rooms')
    if (disposed) return
    roomError.value = ''
    if (!code.value && rooms.value.length) {
      const selected = rooms.value.find((r) => r.status === 'active') || rooms.value[0]
      await router.replace(`/rooms/${selected.public_code}`)
    }
  } catch (e) {
    roomError.value = e instanceof Error ? e.message : 'Не удалось загрузить комнаты'
  } finally {
    if (!disposed) roomTimer = setTimeout(loadRooms, 15000)
  }
}
function selectRoom(event: Event) {
  void router.push(`/rooms/${(event.target as HTMLSelectElement).value}`)
}
onMounted(() => {
  void loadRooms()
})
onUnmounted(() => {
  disposed = true
  clearTimeout(roomTimer)
})
watch(code, () => {
  searching.value = ''
})
</script>
<template>
  <div class="leaderboard-page">
    <div class="page page-body">
      <template v-if="data">
        <div class="room-toolbar">
          <div class="room-name">
            <img
              class="room-logo"
              src="/brand/logo-dark.svg"
              alt="Питерский мостик"
              width="171"
              height="45"
            />
            <div class="room-title">
              <span class="section-eyebrow">ИГРОВАЯ КОМНАТА</span>
              <select
                v-if="rooms.length > 1"
                :value="data.public_code"
                aria-label="Игровая комната"
                @change="selectRoom"
              >
                <option v-for="room in rooms" :key="room.id" :value="room.public_code">
                  {{ room.title }}
                </option>
              </select>
              <h1 v-else>{{ data.title }}</h1>
            </div>
          </div>
          <div class="room-toolbar-actions"><RoomStatus :status="data.status" /></div>
        </div>

        <section class="stats-grid" aria-label="Статистика игры">
          <div class="stat-card">
            <span class="stat-icon"><Users :size="24" /></span>
            <div>
              <span class="stat-label">Участников в игре</span
              ><strong>{{ data.participants_count }}</strong>
            </div>
          </div>
          <div class="stat-card">
            <span class="stat-icon"><Trophy :size="24" /></span>
            <div>
              <span class="stat-label">Лучший результат</span
              ><strong
                >{{ data.leaderboard[0]?.total_score || 0 }}
                <small
                  >/ {{ data.questions_count * data.max_points_per_question }} б.</small
                ></strong
              >
            </div>
          </div>
          <div class="stat-card">
            <span class="stat-icon"><Clock3 :size="24" /></span>
            <div>
              <span class="stat-label">{{
                data.status === 'finished'
                  ? 'Игра завершена'
                  : data.status === 'draft'
                    ? 'До начала игры'
                    : 'До конца игры'
              }}</span
              ><strong
                ><Countdown
                  :ends-at="data.ends_at"
                  :server-time="data.server_time"
                  :status="data.status"
              /></strong>
            </div>
          </div>
        </section>

        <div class="content-grid">
          <section id="rating" class="ranking-panel panel">
            <div class="panel-heading">
              <div>
                <h2>
                  Рейтинг участников <span class="count-pill">{{ data.participants_count }}</span>
                </h2>
              </div>
              <span class="live-label" :class="{ 'live-label--retry': error || roomError }"
                ><span class="tiny-dot" :class="{ 'tiny-dot--retry': error || roomError }"></span
                >{{
                  error || roomError
                    ? 'Попытка получить данные…'
                    : data.status === 'finished'
                      ? 'Итоговый рейтинг'
                      : data.status === 'draft'
                        ? 'Ждём начала'
                        : 'В прямом эфире'
                }}</span
              >
            </div>
            <div v-if="topThree.length" class="podium">
              <div
                v-for="(player, index) in topThree"
                :key="player.participant_id"
                class="podium-card"
                :class="`podium-${index}`"
              >
                <span class="podium-place"
                  >{{ ['01', '02', '03'][index] }} <Trophy v-if="index === 0" :size="19" /></span
                ><span class="podium-name">{{ player.display_name }}</span
                ><strong>{{ player.total_score }}<small> баллов</small></strong>
              </div>
            </div>
            <div class="table-toolbar">
              <span>
                {{ topThree.length ? 'Остальные участники' : 'Все участники' }}
                <ArrowDown :size="14" />
              </span>
              <div class="table-page-status" aria-live="off">
                <span
                  >Страница {{ tablePageStatus.pageIndex }} из {{ tablePageStatus.pageCount }}</span
                >
                <span v-if="tablePageStatus.pageCount > 1">
                  Следующая смена через {{ tablePageStatus.secondsUntilNextPage }} сек.
                </span>
              </div>
              <label class="search">
                <Search :size="17" />
                <input
                  v-model="searching"
                  type="search"
                  placeholder="Найти участника"
                  aria-label="Найти участника"
                />
              </label>
            </div>
            <LeaderboardTable
              :players="filtered"
              :count="data.questions_count"
              :search="searching"
              :has-leaders="topThree.length > 0"
              @page-status="tablePageStatus = $event"
            />
          </section>
          <aside class="game-aside">
            <section v-if="data.status !== 'finished'" class="join-panel panel">
              <span class="section-eyebrow">ПРИСОЕДИНЯЙТЕСЬ</span>
              <h2>Твой ход!</h2>
              <p>Сканируй QR-код<br />и открывай игру в Telegram.</p>
              <div class="qr-wrap">
                <QRCode :value="data.join_url" /><span class="qr-corner top-left"></span
                ><span class="qr-corner bottom-right"></span>
              </div>
              <span class="aside-footnote">Быстрее ответ — больше баллов.</span>
            </section>
            <section v-if="data.status === 'finished'" class="fact-panel">
              <Sparkles :size="25" />
              <h3>Спасибо за игру!</h3>
              <p>
                {{ finishedCount }} участников прошли все вопросы. До встречи на следующем
                мероприятии!
              </p>
            </section>
          </aside>
        </div>
      </template>
      <section v-else-if="loading" class="panel loading-panel" aria-live="polite">
        <RefreshCw class="spin" :size="26" />
        <p>Подключаемся к игре…</p>
      </section>
      <section v-else class="waiting-panel panel">
        <div class="waiting-icon"><Radio :size="32" /></div>
        <span class="section-eyebrow">ВСЁ НАЧИНАЕТСЯ СО ВСТРЕЧИ</span>
        <h2>{{ code ? 'Не удалось открыть комнату' : 'Готовимся к большой игре' }}</h2>
        <p>
          {{
            code
              ? 'Проверьте ссылку комнаты или попробуйте обновить страницу.'
              : 'Организатор скоро откроет комнату. Рейтинг участников появится здесь — присоединяйтесь по QR-коду на стойке.'
          }}
        </p>
        <button class="button primary" @click="refresh">Обновить <RefreshCw :size="17" /></button>
      </section>
    </div>
  </div>
</template>
