<script setup lang="ts">
import { Check, Trophy, Users } from '@lucide/vue'
import type { Player } from '../services/api'
defineProps<{ players: Player[]; count: number; search: string }>()
const colors = ['mint', 'peach', 'lilac', 'blue']
</script>
<template>
  <div v-if="!players.length" class="empty-state">
    <Users :size="36" :stroke-width="1.3" />
    <h3>{{ search ? 'Участник не найден' : 'Первое место пока свободно' }}</h3>
    <p>{{ search ? 'Попробуйте другое имя или никнейм.' : 'Сканируйте QR-код, отвечайте на вопросы и станьте первым в рейтинге.' }}</p>
  </div>
  <div v-else class="table-scroll">
    <table class="leaderboard-table">
      <thead><tr><th>Место</th><th>Участник</th><th>Прогресс</th><th class="right">Баллы</th></tr></thead>
      <tbody>
        <tr v-for="player in players" :key="player.participant_id" :class="{ 'leader-row': player.place === 1 }">
          <td><span class="place" :class="`place-${player.place}`"><Trophy v-if="player.place === 1" :size="17" />{{ player.place }}</span></td>
          <td><div class="player"><span class="avatar" :class="colors[player.participant_id % colors.length]">{{ player.display_name.replace('@', '').slice(0, 2).toUpperCase() }}</span><span class="player-name">{{ player.display_name }}</span><Check v-if="player.completed" class="completed-icon" :size="16" aria-label="Завершил игру" /></div></td>
          <td><div class="progress-cell"><div class="progress-track"><i :style="{ width: `${Math.min(100, player.closed_questions / count * 100)}%` }"></i></div><span>{{ player.closed_questions }}<span class="muted"> / {{ count }}</span></span></div></td>
          <td class="right"><strong class="score-number">{{ player.total_score.toLocaleString('ru-RU') }}</strong><span class="score-unit"> б.</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
