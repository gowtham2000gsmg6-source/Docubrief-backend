import hashlib

from fastapi import HTTPException, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.supabase import get_supabase


def enforce_rate_limit(*, user_id: str, action: str, limit: int) -> None:
    settings = get_settings()
    user_key = hashlib.sha256(user_id.encode()).hexdigest()
    key = f"docubrief:rate:{action}:{user_key}"
    if settings.is_vercel:
        try:
            result = get_supabase().rpc(
                "consume_docubrief_rate_limit",
                {
                    "p_key": f"{action}:{user_key}",
                    "p_limit": limit,
                    "p_window_seconds": settings.rate_limit_window_seconds,
                },
            ).execute()
            data = result.data
            if not isinstance(data, dict) or not isinstance(data.get("allowed"), bool):
                raise RuntimeError("Supabase returned an invalid rate-limit result.")
            if not data["allowed"]:
                retry_after = max(1, int(data.get("retry_after", settings.rate_limit_window_seconds)))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            return
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiting is temporarily unavailable.",
            ) from exc

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, settings.rate_limit_window_seconds)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(settings.rate_limit_window_seconds)},
            )
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting is temporarily unavailable.",
        ) from exc
    finally:
        redis.close()
