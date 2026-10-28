<script setup lang="ts">
import { Users } from '@lucide/vue'
import type { Player } from '../services/api'
defineProps<{ players: Player[]; count: number; search: string; hasLeaders?: boolean }>()
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
  <div v-else class="table-scroll">
    <table class="leaderboard-table">
      <thead>
        <tr>
          <th>Место</th>
          <th>Участник</th>
          <th>Прогресс</th>
          <th class="right">Баллы</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="player in players" :key="player.participant_id">
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
              ><strong class="score-number">{{ player.total_score.toLocaleString('ru-RU') }}</strong
              ><span class="score-unit"> б.</span></template
            ><span v-else class="pending-score">{{
              player.status === 'expired' ? 'Не завершён' : 'В игре'
            }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
