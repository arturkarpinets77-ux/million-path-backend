import time
from fastapi import APIRouter
from app.config import config

router = APIRouter()
START = time.time()

@router.get("/health")
def health():
    return {
        "ok": True,
        "uptime_sec": round(time.time() - START, 2),
        "mode": config.trade_mode,
        "quote": config.quote_asset
    }
