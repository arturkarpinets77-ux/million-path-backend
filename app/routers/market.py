from fastapi import APIRouter, HTTPException
import httpx
from app.config import config

router = APIRouter()

BINANCE_API = "https://api.binance.com"

@router.get("/symbols/usdc")
async def symbols_usdc():
    url = f"{BINANCE_API}/api/v3/exchangeInfo"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    syms = []
    for s in data.get("symbols", []):
        if s.get("status") == "TRADING" and s.get("quoteAsset") == config.quote_asset:
            syms.append(s["symbol"])
    syms.sort()
    return {"quote": config.quote_asset, "count": len(syms), "symbols": syms}
