from fastapi import APIRouter, HTTPException
import httpx
from app.config import config

router = APIRouter()

ENDPOINTS = [
    "https://api.binance.com",
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

HEADERS = {"User-Agent": "million-path/0.1", "Accept": "application/json"}

async def fetch_exchange_info():
    last_err = None
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as client:
        for base in ENDPOINTS:
            try:
                r = await client.get(f"{base}/api/v3/exchangeInfo")
                r.raise_for_status()
                data = r.json()
                # если symbols есть и не пустые — ок
                if isinstance(data, dict) and data.get("symbols"):
                    return data
            except Exception as e:
                last_err = e
                continue
    raise HTTPException(status_code=502, detail=f"Failed to fetch exchangeInfo: {last_err}")

@router.get("/symbols/{quote}")
async def symbols_by_quote(quote: str):
    quote = quote.upper()
    data = await fetch_exchange_info()
    syms = []
    for s in data.get("symbols", []):
        # фильтруем только спот и торгуемые
        if s.get("status") == "TRADING" \
           and s.get("quoteAsset") == quote \
           and ("SPOT" in s.get("permissions", []) or "MARGIN" in s.get("permissions", [])):
            syms.append(s["symbol"])
    syms.sort()
    return {"quote": quote, "count": len(syms), "symbols": syms}

# оставим совместимость со старым путём
@router.get("/symbols/usdc")
async def symbols_usdc():
    return await symbols_by_quote("USDC")
