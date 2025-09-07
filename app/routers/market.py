from fastapi import APIRouter, HTTPException
import httpx
from app.config import config

router = APIRouter()

ENDPOINTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://data-api.binance.vision",
    "https://api-gcp.binance.com",
]

HEADERS = {"User-Agent": "million-path/0.1", "Accept": "application/json"}


async def try_get_json(url: str):
    async with httpx.AsyncClient(timeout=25.0, headers=HEADERS) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def fetch_exchange_info():
    last_err = None
    for base in ENDPOINTS:
        try:
            data = await try_get_json(f"{base}/api/v3/exchangeInfo")
            if isinstance(data, dict) and data.get("symbols"):
                return data
        except Exception as e:
            last_err = e
            continue
    raise HTTPException(status_code=502, detail=f"Failed exchangeInfo: {last_err}")


async def fetch_symbols_from_ticker(quote: str):
    # Фолбэк: берём список всех символов и фильтруем по суффиксу
    last_err = None
    for base in ENDPOINTS:
        try:
            data = await try_get_json(f"{base}/api/v3/ticker/price")
            if isinstance(data, list) and data:
                syms = [x["symbol"] for x in data if isinstance(x, dict) and str(x.get("symbol","")).endswith(quote)]
                syms.sort()
                return syms
        except Exception as e:
            last_err = e
            continue
    raise HTTPException(status_code=502, detail=f"Failed ticker fallback: {last_err}")


@router.get("/symbols/{quote}")
async def symbols_by_quote(quote: str):
    quote = quote.upper()
    # 1) Пробуем exchangeInfo
    try:
        data = await fetch_exchange_info()
        syms = []
        for s in data.get("symbols", []):
            if s.get("status") == "TRADING" and s.get("quoteAsset") == quote:
                syms.append(s["symbol"])
        syms.sort()
        if syms:
            return {"quote": quote, "count": len(syms), "symbols": syms}
    except HTTPException:
        pass  # пойдём на фолбэк

    # 2) Фолбэк по ticker/price
    syms_fb = await fetch_symbols_from_ticker(quote)
    return {"quote": quote, "count": len(syms_fb), "symbols": syms_fb}


# Совместимость со старым путём
@router.get("/symbols/usdc")
async def symbols_usdc():
    return await symbols_by_quote("USDC")


# Отладка: посмотреть, какие котировки доступны и по сколько символов
@router.get("/debug/quotes")
async def debug_quotes():
    data = await fetch_exchange_info()
    counts = {}
    for s in data.get("symbols", []):
        if s.get("status") == "TRADING":
            q = s.get("quoteAsset")
            counts[q] = counts.get(q, 0) + 1
    # Отсортируем по убыванию количества
    items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return {"quotes": items[:50], "unique_quotes": len(counts)}
