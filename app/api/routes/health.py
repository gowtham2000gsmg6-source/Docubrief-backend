import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from redis import Redis

from app.core.config import get_settings
from app.core.supabase import get_supabase

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        settings = get_settings()
        if not settings.is_vercel:
            Redis.from_url(settings.redis_url).ping()
        get_supabase().table("documents").select("id").limit(1).execute()
    except Exception as exc:
        logger.exception("A health dependency check failed", extra={"event": "health_check_failed"})
        raise HTTPException(status_code=503, detail="A required service is unavailable.") from exc
    return HealthResponse(status="ok")
