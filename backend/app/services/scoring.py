def calculate_points(
    *, correct: bool, elapsed_ms: int, limit_seconds: int, maximum: int, minimum: int,
    no_penalty_seconds: int = 0,
):
    if not correct:
        return 0
    elapsed = max(0, elapsed_ms)
    limit_ms = limit_seconds * 1000
    grace_ms = max(0, no_penalty_seconds) * 1000
    if elapsed >= limit_ms:
        return minimum
    if elapsed <= grace_ms:
        return maximum
    billable_ms = elapsed - grace_ms
    decay_window_ms = limit_ms - grace_ms
    return min(maximum, max(minimum, round(maximum * (1 - billable_ms / decay_window_ms))))
