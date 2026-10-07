from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from app.core.config import get_settings

bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(f"{get_settings().supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict[str, Any]:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid Supabase access token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    settings = get_settings()
    if not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase authentication is not configured.",
        )
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=settings.jwt_audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except (PyJWTError, ValueError):
        raise unauthorized from None
    if claims.get("role") != "authenticated":
        raise unauthorized
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise unauthorized
    return claims


UserClaims = Annotated[dict[str, Any], Depends(current_user)]
