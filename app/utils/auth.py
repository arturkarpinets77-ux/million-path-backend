from fastapi import Header, HTTPException, status
from app.config import config

def require_bearer(authorization: str | None = Header(default=None)):
    if not config.app_token:
        return True  # если токен не задан, пропускаем (MVP). Поставь APP_TOKEN в проде!
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != config.app_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
    return True
