# app/routers/market.py
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException

# Пытаемся использовать уже существующие в проекте помощники, если они есть.
# Если их нет — используем локальные определения ниже (через httpx).
try:
    # если в проекте есть свои утилиты, скорректируй путь импорта при необходимости
    from ..core.http import try_get_json, ENDPOINTS  # type: ignore
except Exception:
    import httpx

    # Пулы публичных эндпоинтов Binance для фолбэка
    ENDPOINTS: List[str] = [
        "https://api.binance.com",
        "https://data-api.binance.vision",
    ]

    async def try_get_json(url: str, timeout: float = 10.0) -> Any:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()

router = APIRouter(tags=["market"])

def _to_float(x: Any) -> float:
    try:
        return float(x or 0)
    except Exception:
        return 0.0

def _is_spot_trading_allowed(sym_info: Dict[str, Any]) -> bool:
    # Binance может возвращать либо boolean флаг, либо список permissions
    if sym_info.get("isSpotTradingAllowed"):
        return True
    perms = sym_info.get("permissions") or []
    return "SPOT" in perms

def _good_base_symbol(base: str, exclude_leverage: bool = True) -> bool:
    # Не начинаем с цифры (1000XYZ)
    if not base or base[0].isdigit():
        return False
    if exclude_leverage:
        for suf in ("UP", "DOWN", "BULL", "BEAR"):
            if base.endswith(suf):
                return False
    return True

async def _fetch_exchange_info() -> Dict[str, Any]:
    last_err = None
    for base in ENDPOINTS:
        try:
            data = await try_get_json(f"{base}/api/v3/exchangeInfo")
            if data:
                return data
        except Exception as e:
            last_err = e
            continue
    raise HTTPException(status_code=502, detail=f"Failed to fetch exchangeInfo: {last_err}")

async def _fetch_24h_tickers() -> List[Dict[str, Any]]:
    last_err = None
    for base in ENDPOINTS:
        try:
            data = await try_get_json(f"{base}/api/v3/ticker/24hr")
            if isinstance(data, list) and data:
                return data
        except Exception as e:
            last_err = e
            continue
    raise HTTPException(status_code=502, detail=f"Failed to fetch 24h tickers: {last_err}")

@router.get("/symbols/{quote}")
async def symbols_by_quote(quote: str) -> Dict[str, Any]:
    """
    Список всех СПОТ-символов со статусом TRADING для заданной котировки (например, USDC).
    """
    quote = quote.upper()
    exch = await _fetch_exchange_info()

    symbols: List[str] = []
    for s in exch.get("symbols", []):
        sym = s.get("symbol")
        if not isinstance(sym, str):
            continue
        if s.get("status") != "TRADING":
            continue
        if not _is_spot_trading_allowed(s):
            continue
        if not sym.endswith(quote):
            continue
        base = sym[: -len(quote)]
        if not _good_base_symbol(base, exclude_leverage=True):
            continue
        symbols.append(sym)

    # Убираем возможные дубли
    symbols = list(dict.fromkeys(symbols))
    return {"quote": quote, "count": len(symbols), "symbols": symbols}

@router.get("/symbols/{quote}/top")
async def symbols_top_by_quote(
    quote: str,
    n: int = 20,
    min_qvol: float = 500_000,
    exclude_leverage: bool = True,
) -> Dict[str, Any]:
    """
    Топ ликвидных СПОТ-символов для заданной котировки (например, USDC).
    Основано на /api/v3/exchangeInfo и /api/v3/ticker/24hr Binance.
    Фильтры:
      - status == TRADING
      - spot trading allowed
      - base не начинается с цифры
      - исключаем UP/DOWN/BULL/BEAR при exclude_leverage=True
      - порог ликвидности по quoteVolume >= min_qvol
    Сортировка: по (quoteVolume, count) убыв.
    """
    quote = quote.upper()
    exch = await _fetch_exchange_info()
    tickers = await _fetch_24h_tickers()

    # валидный спот TRADING
    valid_spot = set()
    for s in exch.get("symbols", []):
        sym = s.get("symbol")
        if not isinstance(sym, str):
            continue
        if s.get("status") == "TRADING" and _is_spot_trading_allowed(s):
            valid_spot.add(sym)

    def is_good_symbol(sym: str) -> bool:
        if not sym.endswith(quote):
            return False
        base = sym[: -len(quote)]
        return _good_base_symbol(base, exclude_leverage=exclude_leverage)

    filtered: List[Dict[str, Any]] = [
        t for t in tickers
        if isinstance(t.get("symbol"), str)
        and t["symbol"] in valid_spot
        and is_good_symbol(t["symbol"])
        and _to_float(t.get("quoteVolume")) >= float(min_qvol)
    ]

    # сортируем по ликвидности и количеству сделок
    filtered.sort(key=lambda t: (_to_float(t.get("quoteVolume")), _to_float(t.get("count"))), reverse=True)

    n = max(1, min(int(n), 200))
    symbols = [t["symbol"] for t in filtered[:n]]
    return {"quote": quote, "n": len(symbols), "symbols": symbols}
