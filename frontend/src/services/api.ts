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
  participant_id: number; place: number | null; display_name: string;
  total_score: number | null; closed_questions: number; completed: boolean;
  status: 'playing' | 'completed' | 'expired';
}
export interface Leaderboard extends Room { room_id: number; leaderboard: Player[] }
export interface Category { id: number; name: string; slug: string; description?: string }
export interface AdminUser {
  id: number; telegram_id: number; username: string | null; first_name: string; last_name: string | null;
  attempts_count: number; rooms_count: number; completed_count: number; answered_count: number;
  last_seen: string | null; available_grants: number;
}
export interface UserDetail {
  user: Pick<AdminUser, 'id' | 'telegram_id' | 'username' | 'first_name' | 'last_name'> & { created_at: string };
  grants: { available: number; issued: number; consumed: number; history: { id: number; granted_at: string; used_at: string | null; participant_id: number | null }[] };
  attempts: {
    participant_id: number; room_id: number; room_title: string; room_status: string; status: string;
    total_score: number; current_question_number: number; questions_count: number; answered_count: number;
    joined_at: string; deadline_at: string | null; completed_at: string | null;
    questions: {
      position: number; text: string; explanation: string; status: string; sent_at: string | null;
      selected_option: string | null; correct_option: string | null; is_correct: boolean | null;
      points: number | null; response_time_ms: number | null;
    }[];
  }[];
}
export interface Question {
  id: number; category_id: number; text: string; explanation: string; company: string | null;
  difficulty: number; time_limit_seconds: number | null; no_penalty_seconds: number; is_active: boolean; locked: boolean;
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
