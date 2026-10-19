def calculate_points(*, correct: bool, elapsed_ms: int, limit_seconds: int, maximum: int, minimum: int):
    if not correct or elapsed_ms >= limit_seconds * 1000:
        return 0
    return min(maximum, max(minimum, round(maximum * (1 - max(0, elapsed_ms) / (limit_seconds * 1000)))))
