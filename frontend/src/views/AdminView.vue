<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ArrowRight, Check, Copy, ExternalLink, KeyRound, LockKeyhole, LogOut, Pencil, Play, Plus, Search, Square, X } from '@lucide/vue'
import { adminApi, setAdminKey, type Category, type Question, type Room } from '../services/api'
import QRCode from '../components/QRCode.vue'
import RoomStatus from '../components/RoomStatus.vue'

const loggedIn = ref(false), key = ref(''), busy = ref(false), error = ref(''), success = ref('')
const tab = ref('rooms'), rooms = ref<Room[]>([]), questions = ref<Question[]>([]), categories = ref<Category[]>([])
const search = ref(''), roomDialog = ref(false), questionDialog = ref(false), qrRoom = ref<Room | null>(null)
const editingRoom = ref<number | null>(null), editingQuestion = ref<number | null>(null)
const selectedQuestions = ref<number[]>([])
const roomForm = reactive({ title: '', duration_minutes: 60, questions_count: 10, question_time_limit_seconds: 30, max_points_per_question: 100, min_correct_points: 0 })
const questionForm = reactive({ category_id: 0, text: '', explanation: '', company: '', difficulty: 1, time_limit_seconds: null as number | null, is_active: true, options: [{ text: '', is_correct: true }, { text: '', is_correct: false }] })
const categoryForm = reactive({ name: '', slug: '' })
const categoryDialog = ref(false)
const questionSearch = ref('')
const filteredQuestions = computed(() => questions.value.filter(q => q.text.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())))
const selectableQuestions = computed(() => questions.value.filter(q => q.is_active && q.text.toLocaleLowerCase().includes(questionSearch.value.toLocaleLowerCase())))
const companyNames: Record<string, string> = { svyazkom: 'Связьком', sensory_hub: 'Sensory Hub', systematics: 'Систематикс', galaxy: 'Galaxy' }

async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; success.value = ''
  try { await action() } catch (e) { error.value = e instanceof Error ? e.message : 'Не удалось выполнить действие' }
  finally { busy.value = false }
}
async function load() {
  const result = await Promise.all([adminApi<Room[]>('/rooms'), adminApi<Question[]>('/questions'), adminApi<Category[]>('/categories')])
  ;[rooms.value, questions.value, categories.value] = result
}
function login() {
  void run(async () => { setAdminKey(key.value); await load(); loggedIn.value = true; key.value = '' })
}
function logout() { loggedIn.value = false; setAdminKey(''); rooms.value = []; questions.value = []; categories.value = [] }
function newRoom() {
  editingRoom.value = null
  Object.assign(roomForm, { title: '', duration_minutes: 60, questions_count: 10, question_time_limit_seconds: 30, max_points_per_question: 100, min_correct_points: 0 })
  selectedQuestions.value = questions.value.filter(q => q.is_active).map(q => q.id)
  questionSearch.value = ''; roomDialog.value = true
}
function editRoom(room: Room) {
  void run(async () => {
    const detail = await adminApi<Room>(`/rooms/${room.id}`)
    editingRoom.value = room.id
    Object.assign(roomForm, { title: detail.title, duration_minutes: detail.duration_minutes, questions_count: detail.questions_count, question_time_limit_seconds: detail.question_time_limit_seconds, max_points_per_question: detail.max_points_per_question, min_correct_points: detail.min_correct_points })
    selectedQuestions.value = detail.question_ids || []
    questionSearch.value = ''; roomDialog.value = true
  })
}
function saveRoom() {
  void run(async () => {
    const saved = await adminApi<Room>(editingRoom.value ? `/rooms/${editingRoom.value}` : '/rooms', editingRoom.value ? 'PATCH' : 'POST', roomForm)
    // Keep the newly created draft ID if saving its bank fails, so retry does not duplicate rooms.
    editingRoom.value = saved.id
    await adminApi(`/rooms/${saved.id}/questions`, 'POST', { question_ids: selectedQuestions.value })
    roomDialog.value = false; await load(); success.value = 'Черновик комнаты сохранён'
  })
}
function startRoom(room: Room) {
  void run(async () => { await adminApi(`/rooms/${room.id}/start`, 'POST'); await load(); success.value = 'Комната открыта. Участники могут присоединяться по QR-коду.' })
}
const finishTarget = ref<Room | null>(null)
function finishRoom() {
  if (!finishTarget.value) return
  const id = finishTarget.value.id
  void run(async () => { await adminApi(`/rooms/${id}/finish`, 'POST'); finishTarget.value = null; await load(); success.value = 'Игра завершена, результаты зафиксированы' })
}
function newQuestion(source?: Question, copy = false) {
  editingQuestion.value = source && !copy ? source.id : null
  Object.assign(questionForm, source ? {
    category_id: source.category_id, text: source.text, explanation: source.explanation,
    company: source.company || '', difficulty: source.difficulty,
    time_limit_seconds: source.time_limit_seconds, is_active: source.is_active,
    options: source.options.map(o => ({ text: o.text, is_correct: o.is_correct })),
  } : { category_id: categories.value[0]?.id || 0, text: '', explanation: '', company: '', difficulty: 1,
    time_limit_seconds: null, is_active: true, options: [{ text: '', is_correct: true }, { text: '', is_correct: false }] })
  questionDialog.value = true
}
function selectCorrect(index: number) { questionForm.options.forEach((o, i) => { o.is_correct = i === index }) }
function removeOption(index: number) {
  questionForm.options.splice(index, 1)
  if (!questionForm.options.some(o => o.is_correct)) questionForm.options[0].is_correct = true
}
function saveQuestion() {
  void run(async () => {
    await adminApi(editingQuestion.value ? `/questions/${editingQuestion.value}` : '/questions', editingQuestion.value ? 'PATCH' : 'POST', {
      ...questionForm, company: questionForm.company || null,
      time_limit_seconds: questionForm.time_limit_seconds || null,
    })
    questionDialog.value = false; await load(); success.value = 'Вопрос сохранён'
  })
}
function saveCategory() {
  void run(async () => { await adminApi('/categories', 'POST', categoryForm); categoryDialog.value = false; categoryForm.name = ''; categoryForm.slug = ''; await load(); success.value = 'Категория добавлена' })
}
async function copyLink(value: string) {
  try { await navigator.clipboard.writeText(value); success.value = 'Ссылка скопирована' }
  catch { error.value = 'Не удалось скопировать автоматически. Выделите ссылку в окне QR-кода.' }
}
</script>
<template>
  <div class="page admin-page">
    <div class="page-eyebrow"><span class="tiny-dot"></span> ЗА КУЛИСАМИ ИГРЫ</div>
    <div class="page-heading"><div><h1>Кабинет организатора<span class="heading-dot">.</span></h1><p>Всё для игры, которая объединяет.</p></div><button v-if="loggedIn" class="button subtle" @click="logout"><LogOut :size="16" />Выйти</button></div>
    <div v-if="error" class="notice error" role="alert">{{ error }}<button class="icon-button" aria-label="Закрыть сообщение" @click="error = ''"><X :size="16" /></button></div>
    <div v-if="success" class="notice success" role="status">{{ success }}<button class="icon-button" aria-label="Закрыть сообщение" @click="success = ''"><X :size="16" /></button></div>
    <form v-if="!loggedIn" class="login-panel panel" @submit.prevent="login"><span class="login-icon"><LockKeyhole :size="27" /></span><h2>Здесь начинается игра</h2><p>Введите ключ организатора, чтобы управлять комнатами и вопросами.</p><label>Ключ администратора<input v-model="key" type="password" autocomplete="current-password" placeholder="Введите ключ доступа" required /></label><button class="button dark" :disabled="busy">{{ busy ? 'Проверяем…' : 'Войти в кабинет' }}<ArrowRight :size="17" /></button><span class="muted small"><KeyRound :size="13" /> Ключ задаётся в настройке ADMIN_SECRET</span></form>
    <template v-else>
      <div class="admin-toolbar"><div class="tabs" role="tablist" aria-label="Разделы кабинета"><button :class="{ active: tab === 'rooms' }" role="tab" :aria-selected="tab === 'rooms'" @click="tab = 'rooms'">Комнаты <span>{{ rooms.length }}</span></button><button :class="{ active: tab === 'questions' }" role="tab" :aria-selected="tab === 'questions'" @click="tab = 'questions'">Банк вопросов <span>{{ questions.length }}</span></button></div><div class="toolbar-actions"><button v-if="tab === 'questions'" class="button subtle" @click="categoryDialog = true"><Plus :size="16" />Категория</button><button class="button dark" @click="tab === 'rooms' ? newRoom() : newQuestion()"><Plus :size="17" />{{ tab === 'rooms' ? 'Новая комната' : 'Добавить вопрос' }}</button></div></div>
      <section v-if="tab === 'rooms'" class="room-grid"><div v-if="!rooms.length" class="panel empty-state"><h3>Первая игра начинается здесь</h3><p>Добавьте вопросы, создайте комнату и пригласите участников.</p><button class="button dark" @click="newRoom">Создать комнату <Plus :size="16" /></button></div><article v-for="room in rooms" :key="room.id" class="room-card panel"><div class="room-card-top"><RoomStatus :status="room.status" /><span class="muted small">№ {{ room.id }}</span></div><h2>{{ room.title }}</h2><p>{{ room.questions_count }} вопросов · до {{ room.questions_count * room.max_points_per_question }} баллов</p><div class="room-card-stats"><span><strong>{{ room.participants_count }}</strong> участников</span><span>{{ room.ends_at ? `До ${new Date(room.ends_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}` : 'Ожидает запуска' }}</span></div><div class="room-card-actions"><button v-if="room.status === 'draft'" class="button dark" :disabled="busy" @click="startRoom(room)"><Play :size="14" />Запустить</button><button v-if="room.status === 'draft'" class="button subtle" :disabled="busy" @click="editRoom(room)"><Pencil :size="14" />Настроить</button><button v-if="room.status === 'active'" class="button danger" :disabled="busy" @click="finishTarget = room"><Square :size="13" />Завершить</button><button class="button subtle" @click="qrRoom = room">QR-код</button><RouterLink :to="`/rooms/${room.public_code}`" class="icon-button" aria-label="Открыть рейтинг"><ExternalLink :size="17" /></RouterLink></div></article></section>
      <section v-else class="panel question-bank"><div class="bank-toolbar"><h2>Вопросы и объяснения</h2><label class="search"><Search :size="15" /><input v-model="search" type="search" placeholder="Поиск по вопросам" aria-label="Поиск по вопросам" /></label></div><div v-if="!filteredQuestions.length" class="empty-state"><h3>{{ search ? 'Вопросы не найдены' : 'Банк вопросов пока пуст' }}</h3><p>Для первой комнаты понадобится минимум 10 вопросов. У каждого должен быть один верный ответ и объяснение.</p></div><article v-for="question in filteredQuestions" :key="question.id" class="question-item"><div><div class="question-tags"><span>{{ categories.find(c => c.id === question.category_id)?.name }}</span><span v-if="question.company">{{ companyNames[question.company] }}</span><span v-if="question.locked"><LockKeyhole :size="11" />Используется</span><span v-if="!question.is_active">Неактивен</span></div><h3>{{ question.text }}</h3><p>{{ question.explanation }}</p><div class="answer-preview"><span v-for="(option, i) in question.options" :key="i" :class="{ correct: option.is_correct }"><Check v-if="option.is_correct" :size="12" />{{ option.text }}</span></div></div><button class="icon-button" :aria-label="question.locked ? 'Создать копию вопроса' : 'Редактировать вопрос'" @click="newQuestion(question, question.locked)"><component :is="question.locked ? Copy : Pencil" :size="18" /></button></article></section>
    </template>

    <div v-if="roomDialog" class="modal-backdrop" @click.self="!busy && (roomDialog = false)"><section class="modal wide-modal" role="dialog" aria-modal="true" aria-labelledby="room-dialog-title"><div class="modal-heading"><div><span class="section-eyebrow">ПРОСТРАНСТВО ДЛЯ СОРЕВНОВАНИЯ</span><h2 id="room-dialog-title">{{ editingRoom ? 'Настройки комнаты' : 'Новая комната' }}</h2></div><button class="icon-button" :disabled="busy" aria-label="Закрыть" @click="roomDialog = false"><X :size="21" /></button></div><form @submit.prevent="saveRoom"><label>Название комнаты<input v-model="roomForm.title" required maxlength="255" placeholder="Например, День партнёров" autofocus /></label><div class="form-grid"><label>Длительность, мин<input v-model.number="roomForm.duration_minutes" type="number" min="1" max="1440" required /></label><label>Вопросов на участника<input v-model.number="roomForm.questions_count" type="number" min="1" max="100" required /></label><label>Время ответа, сек<input v-model.number="roomForm.question_time_limit_seconds" type="number" min="1" max="3600" required /></label><label>Максимум за вопрос<input v-model.number="roomForm.max_points_per_question" type="number" min="1" max="10000" required /></label><label>Минимум за верный ответ<input v-model.number="roomForm.min_correct_points" type="number" min="0" :max="roomForm.max_points_per_question" required /></label></div><div class="selection-heading"><h3>Вопросы комнаты <span class="count-pill">{{ selectedQuestions.length }}</span></h3><button type="button" class="text-button" @click="selectedQuestions = selectedQuestions.length ? [] : questions.filter(q => q.is_active).map(q => q.id)">{{ selectedQuestions.length ? 'Снять все' : 'Выбрать все' }}</button></div><input v-model="questionSearch" type="search" placeholder="Найти вопрос в банке" aria-label="Найти вопрос в банке" /><div class="question-selection"><label v-for="q in selectableQuestions" :key="q.id" class="checkbox-label"><input v-model="selectedQuestions" type="checkbox" :value="q.id" /><span>{{ q.text }}</span></label><p v-if="!selectableQuestions.length" class="muted">Нет подходящих вопросов. Добавьте их в банк.</p></div><p class="muted small">До запуска выберите не менее {{ roomForm.questions_count }} активных вопросов. После запуска настройки фиксируются.</p><div v-if="error" class="notice error" role="alert">{{ error }}</div><div class="modal-actions"><button type="button" class="button subtle" :disabled="busy" @click="roomDialog = false">Отмена</button><button class="button dark" :disabled="busy">{{ busy ? 'Сохраняем…' : 'Сохранить черновик' }}</button></div></form></section></div>

    <div v-if="questionDialog" class="modal-backdrop" @click.self="!busy && (questionDialog = false)"><section class="modal wide-modal" role="dialog" aria-modal="true" aria-labelledby="question-dialog-title"><div class="modal-heading"><h2 id="question-dialog-title">{{ editingQuestion ? 'Редактирование вопроса' : 'Новый вопрос' }}</h2><button class="icon-button" :disabled="busy" aria-label="Закрыть" @click="questionDialog = false"><X :size="21" /></button></div><form @submit.prevent="saveQuestion"><div class="form-grid"><label>Категория<select v-model.number="questionForm.category_id" required><option :value="0" disabled>Выберите категорию</option><option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option></select></label><label>Компания<select v-model="questionForm.company"><option value="">Общий вопрос</option><option v-for="(name, value) in companyNames" :key="value" :value="value">{{ name }}</option></select></label></div><label>Текст вопроса<textarea v-model="questionForm.text" required maxlength="1200" rows="3" /></label><label>Почему ответ правильный<textarea v-model="questionForm.explanation" required maxlength="1200" rows="3" placeholder="Краткое объяснение, которое увидит участник" /></label><div class="selection-heading"><h3>Варианты ответа</h3><span class="muted small">Отметьте один верный</span></div><div v-for="(option, i) in questionForm.options" :key="i" class="option-input"><input type="radio" name="correct-answer" :checked="option.is_correct" :aria-label="`Вариант ${i + 1} правильный`" @change="selectCorrect(i)" /><input v-model="option.text" required maxlength="200" :placeholder="`Вариант ${i + 1}`" :aria-label="`Текст варианта ${i + 1}`" /><button v-if="questionForm.options.length > 2" type="button" class="icon-button" aria-label="Удалить вариант" @click="removeOption(i)"><X :size="17" /></button></div><button v-if="questionForm.options.length < 8" type="button" class="text-button" @click="questionForm.options.push({ text: '', is_correct: false })"><Plus :size="15" />Добавить вариант</button><div class="form-grid"><label>Сложность (1–5)<input v-model.number="questionForm.difficulty" type="number" min="1" max="5" required /></label><label>Особый таймер, сек<input v-model.number="questionForm.time_limit_seconds" type="number" min="1" max="3600" placeholder="По настройкам комнаты" /></label></div><label class="checkbox-label"><input v-model="questionForm.is_active" type="checkbox" />Вопрос активен</label><div v-if="error" class="notice error" role="alert">{{ error }}</div><div class="modal-actions"><button type="button" class="button subtle" :disabled="busy" @click="questionDialog = false">Отмена</button><button class="button dark" :disabled="busy">{{ busy ? 'Сохраняем…' : 'Сохранить вопрос' }}</button></div></form></section></div>

    <div v-if="categoryDialog" class="modal-backdrop" @click.self="!busy && (categoryDialog = false)"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="category-dialog-title"><div class="modal-heading"><h2 id="category-dialog-title">Новая категория</h2><button class="icon-button" aria-label="Закрыть" @click="categoryDialog = false"><X :size="20" /></button></div><form @submit.prevent="saveCategory"><label>Название<input v-model="categoryForm.name" required maxlength="100" /></label><label>Код латиницей<input v-model="categoryForm.slug" required maxlength="100" pattern="[a-z0-9_-]+" placeholder="например, networking" /></label><div v-if="error" class="notice error" role="alert">{{ error }}</div><div class="modal-actions"><button class="button dark" :disabled="busy">Добавить категорию</button></div></form></section></div>

    <div v-if="qrRoom" class="modal-backdrop" @click.self="qrRoom = null"><section class="modal qr-modal" role="dialog" aria-modal="true" aria-labelledby="qr-dialog-title"><div class="modal-heading"><h2 id="qr-dialog-title">Вход в игру</h2><button class="icon-button" aria-label="Закрыть" @click="qrRoom = null"><X :size="20" /></button></div><p>{{ qrRoom.title }}</p><QRCode :value="qrRoom.join_url" /><a class="qr-url" :href="qrRoom.join_url" target="_blank" rel="noopener">{{ qrRoom.join_url }}</a><button class="button dark" @click="copyLink(qrRoom.join_url)"><Copy :size="15" />Скопировать ссылку</button></section></div>

    <div v-if="finishTarget" class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="finish-dialog-title"><h2 id="finish-dialog-title">Завершить «{{ finishTarget.title }}»?</h2><p>Участники больше не смогут отвечать. Набранные баллы сохранятся, рейтинг станет итоговым.</p><div class="modal-actions"><button class="button subtle" :disabled="busy" @click="finishTarget = null">Продолжить игру</button><button class="button danger" :disabled="busy" @click="finishRoom">Завершить</button></div></section></div>
  </div>
</template>
