<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, ArrowRight, ArrowUpRight, Clock3, Expand, Radio, RefreshCw, Search, Sparkles, Trophy, Users, X } from '@lucide/vue'
import { api, type Room } from '../services/api'
import { useLeaderboardPolling } from '../composables/useLeaderboardPolling'
import LeaderboardTable from '../components/LeaderboardTable.vue'
import QRCode from '../components/QRCode.vue'
import Countdown from '../components/Countdown.vue'
import RoomStatus from '../components/RoomStatus.vue'

const route = useRoute(), router = useRouter()
const rooms = ref<Room[]>([])
const roomError = ref('')
const searching = ref('')
const fullscreen = ref(false)
const code = computed(() => String(route.params.code || ''))
const { data, error, loading, updatedAt, refresh } = useLeaderboardPolling(code)
const filtered = computed(() => data.value?.leaderboard.filter(p => p.display_name.toLocaleLowerCase().includes(searching.value.toLocaleLowerCase())) || [])
const finishedCount = computed(() => data.value?.leaderboard.filter(p => p.completed).length || 0)
const topThree = computed(() => data.value?.leaderboard.slice(0, 3) || [])
let roomTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false

async function loadRooms() {
  try {
    rooms.value = await api<Room[]>('/rooms')
    roomError.value = ''
    if (!code.value && rooms.value.length) {
      const selected = rooms.value.find(r => r.status === 'active') || rooms.value[0]
      await router.replace(`/rooms/${selected.public_code}`)
    }
  } catch (e) { roomError.value = e instanceof Error ? e.message : 'Не удалось загрузить комнаты' }
  finally { if (!disposed) roomTimer = setTimeout(loadRooms, 15000) }
}
function selectRoom(event: Event) { void router.push(`/rooms/${(event.target as HTMLSelectElement).value}`) }
async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await document.documentElement.requestFullscreen()
  } catch { fullscreen.value = !fullscreen.value }
}
function syncFullscreen() { fullscreen.value = !!document.fullscreenElement }
onMounted(() => { void loadRooms(); document.addEventListener('fullscreenchange', syncFullscreen) })
onUnmounted(() => { disposed = true; clearTimeout(roomTimer); document.removeEventListener('fullscreenchange', syncFullscreen) })
watch(code, () => { searching.value = '' })
</script>
<template>
  <div class="page leaderboard-page" :class="{ 'presentation-mode': fullscreen }">
    <div class="page-eyebrow"><span class="tiny-dot"></span> ВСТРЕЧАЕМСЯ НА СТОРОНЕ ТЕХНОЛОГИЙ</div>
    <div class="page-heading"><div><h1>IT Challenge<span class="heading-dot">.</span></h1><p>Ваши знания. Ваша скорость. Ваше место среди лучших.</p></div><button class="button subtle fullscreen-button" @click="toggleFullscreen"><component :is="fullscreen ? X : Expand" :size="16" />{{ fullscreen ? 'Обычный вид' : 'На весь экран' }}</button></div>

    <section class="challenge-banner">
      <div class="banner-copy"><span class="banner-kicker"><Sparkles :size="15" /> СОЕДИНЯЕМ ЛЮБОПЫТСТВО И АЗАРТ</span><h2>Наведи мосты<br />к новым знаниям.</h2><p>{{ data?.questions_count || 10 }} вопросов о технологиях, людях и идеях.<br />Присоединяйтесь в Telegram — игра уже рядом.</p><a v-if="data?.status === 'active'" :href="data.join_url" target="_blank" rel="noopener" class="button lime">Присоединиться к игре <ArrowUpRight :size="18" /></a><span v-else class="banner-note">{{ data?.status === 'finished' ? 'Игра окончена. Спасибо за участие!' : 'Скоро здесь начнётся большая игра' }}</span></div>
      <div class="bridge-art" aria-hidden="true"><span class="art-orbit orbit-one"></span><span class="art-orbit orbit-two"></span><div class="art-star">✳</div><svg viewBox="0 0 500 280"><path d="M0 224h500M0 242h500M0 260h500" stroke="#8eb7aa" stroke-width="1" opacity=".3"/><path d="M50 220V55m330 165V55M50 82Q215 305 380 82M50 115Q215 319 380 115M0 220h490" fill="none" stroke="#c5e8af" stroke-width="5"/><path d="M50 82 10 196m370-114 100 114M90 125v95m41-61v61m42-40v40m42-33v33m41-40v40m41-61v61m41-95v95" stroke="#c5e8af" stroke-width="3"/><path d="M41 220V55h18v165m312 0V55h18v165" fill="#bfdda8"/><circle cx="416" cy="77" r="30" fill="#f4ab88"/><path d="m401 78 10 10 19-23" stroke="#173e36" fill="none" stroke-width="3"/><rect x="140" y="29" width="121" height="43" rx="11" fill="#eff4df" transform="rotate(-8 140 29)"/><text x="156" y="53" fill="#294b3c" font-family="sans-serif" font-size="16" font-weight="700" transform="rotate(-8 140 29)">&lt;hello, world/&gt;</text></svg><span class="art-caption">59°56′ N · 30°19′ E</span></div>
    </section>

    <div v-if="roomError || error" class="notice error" role="alert"><span>{{ data ? 'Не удалось обновить рейтинг. Показываем последние данные.' : roomError || error }}</span><button class="text-button" @click="refresh">Повторить <RefreshCw :size="14" /></button></div>

    <template v-if="data">
      <div class="room-toolbar"><div class="room-name"><Radio :size="19" /><select v-if="rooms.length > 1" :value="data.public_code" aria-label="Игровая комната" @change="selectRoom"><option v-for="room in rooms" :key="room.id" :value="room.public_code">{{ room.title }}</option></select><h2 v-else>{{ data.title }}</h2></div><RoomStatus :status="data.status" /></div>
      <section class="stats-grid" aria-label="Статистика игры"><div class="stat-card"><span class="stat-icon mint"><Users :size="20" /></span><div><span class="stat-label">В игре</span><strong>{{ data.participants_count }} <small>участников</small></strong></div></div><div class="stat-card"><span class="stat-icon peach"><Trophy :size="20" /></span><div><span class="stat-label">Лучший результат</span><strong>{{ data.leaderboard[0]?.total_score || 0 }} <small>/ {{ data.questions_count * data.max_points_per_question }} б.</small></strong></div></div><div class="stat-card"><span class="stat-icon lilac"><Clock3 :size="20" /></span><div><span class="stat-label">{{ data.status === 'finished' ? 'Игра завершена' : 'До конца игры' }}</span><strong><Countdown :ends-at="data.ends_at" :server-time="data.server_time" :status="data.status" /></strong></div></div></section>
      <div class="content-grid">
        <section class="ranking-panel panel">
          <div class="panel-heading"><div><div class="section-eyebrow">ЗНАНИЯ РЕШАЮТ</div><h2>Рейтинг участников <span class="count-pill">{{ data.participants_count }}</span></h2></div><span class="live-label"><span class="tiny-dot"></span>{{ data.status === 'finished' ? 'Итоговый' : 'В прямом эфире' }}</span></div>
          <div v-if="topThree.length" class="podium"><div v-for="(player, index) in topThree" :key="player.participant_id" class="podium-card" :class="`podium-${index}`"><span class="podium-place">{{ ['01', '02', '03'][index] }} <Trophy v-if="index === 0" :size="17" /></span><span class="podium-name">{{ player.display_name }}</span><strong>{{ player.total_score }}<small> баллов</small></strong></div></div>
          <div class="table-toolbar"><span>Все участники <ArrowDown :size="13" /></span><label class="search"><Search :size="15" /><input v-model="searching" type="search" placeholder="Найти участника" aria-label="Найти участника" /></label></div>
          <LeaderboardTable :players="filtered" :count="data.questions_count" :search="searching" />
          <div class="table-footer"><span><RefreshCw :size="12" />{{ data.status === 'finished' ? 'Результаты зафиксированы' : 'Обновление каждые 15 секунд' }}</span><span>{{ updatedAt ? `Обновлено в ${updatedAt.toLocaleTimeString('ru-RU')}` : '' }}</span></div>
        </section>
        <aside class="game-aside"><section v-if="data.status !== 'finished'" class="join-panel panel"><span class="section-eyebrow">ВАШ СЛЕДУЮЩИЙ ВЫЗОВ</span><h2>Попробуем?</h2><p>Наведите камеру на QR-код<br />и откройте игру в Telegram.</p><div class="qr-wrap"><QRCode :value="data.join_url" /><span class="qr-corner top-left"></span><span class="qr-corner bottom-right"></span></div><a :href="data.join_url" class="telegram-link" target="_blank" rel="noopener">Открыть Telegram <ArrowUpRight :size="15" /></a><div class="join-divider"></div><div class="how-step"><span>01</span>Сканируйте QR-код</div><div class="how-step"><span>02</span>Отвечайте на вопросы</div><div class="how-step"><span>03</span>Следите за результатом</div><span class="aside-footnote">Быстрее ответ — больше баллов.</span></section><section class="fact-panel"><Sparkles :size="20" /><h3>{{ data.status === 'finished' ? 'Спасибо за игру!' : 'Не только код' }}</h3><p>{{ data.status === 'finished' ? `${finishedCount} участников прошли все вопросы. До встречи на следующем мероприятии!` : 'Здесь пригодятся логика, любопытство и общение с командой стенда. Задавайте вопросы — наводите мосты.' }}</p></section></aside>
      </div>
    </template>
    <section v-else-if="loading" class="panel loading-panel" aria-live="polite"><RefreshCw class="spin" :size="24" /><p>Подключаемся к игре…</p></section>
    <section v-else class="waiting-panel panel"><div class="waiting-icon"><Radio :size="30" /></div><span class="section-eyebrow">ВСЁ НАЧИНАЕТСЯ СО ВСТРЕЧИ</span><h2>{{ code ? 'Не удалось открыть комнату' : 'Готовимся к большой игре' }}</h2><p>{{ code ? 'Проверьте ссылку комнаты или попробуйте обновить страницу.' : 'Организатор скоро откроет комнату. Рейтинг участников появится здесь — присоединяйтесь по QR-коду на стойке.' }}</p><RouterLink v-if="!code" to="/admin" class="button dark">Кабинет организатора <ArrowRight :size="16" /></RouterLink><button v-else class="button dark" @click="refresh">Обновить <RefreshCw :size="16" /></button></section>
    <div class="partners"><span>ЧЕТЫРЕ КОМАНДЫ. ОДИН МОСТИК.</span><div class="partner-logos"><b class="svyazkom">связьком<span>↗</span></b><b class="sensory">sensory<span>hub</span></b><b class="systematics">▦ систематикс</b><b class="galaxy">✳ galaxy</b></div></div>
  </div>
</template>
