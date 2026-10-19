export interface Room {
  id: number; public_code: string; title: string;
  status: 'draft' | 'active' | 'finished' | 'cancelled';
  starts_at: string | null; ends_at: string | null; server_time: string;
  participants_count: number; questions_count: number; max_points_per_question: number;
  join_url: string; public_url: string;
  duration_minutes?: number; question_time_limit_seconds?: number;
  min_correct_points?: number; question_ids?: number[];
}
export interface Player {
  participant_id: number; place: number; display_name: string;
  total_score: number; closed_questions: number; completed: boolean;
}
export interface Leaderboard extends Room { room_id: number; leaderboard: Player[] }
export interface Category { id: number; name: string; slug: string; description?: string }
export interface Question {
  id: number; category_id: number; text: string; explanation: string; company: string | null;
  difficulty: number; time_limit_seconds: number | null; is_active: boolean; locked: boolean;
  options: { text: string; is_correct: boolean; id?: number }[];
}

let adminKey = ''
export function setAdminKey(value: string) { adminKey = value }
export async function api<T>(path: string, options: RequestInit = {}, admin = false): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  if (admin) headers.set('Authorization', `Bearer ${adminKey}`)
  const response = await fetch(`/api${path}`, { ...options, headers, cache: 'no-store' })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    const message = typeof data.detail === 'string' ? data.detail :
      Array.isArray(data.detail) ? data.detail.map((e: { msg: string }) => e.msg).join('; ') : `Ошибка ${response.status}`
    throw new Error(message)
  }
  return response.json()
}
export function adminApi<T>(path: string, method = 'GET', body?: unknown) {
  return api<T>(`/admin${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) }, true)
}
