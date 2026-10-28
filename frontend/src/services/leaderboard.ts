import type { Player } from './api'

export function splitLeaderboard(players: Player[]) {
  return {
    podium: players.filter((p) => p.completed && p.place !== null && p.place <= 3),
    table: players.filter((p) => !p.completed || p.place === null || p.place > 3),
  }
}
