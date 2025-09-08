from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json, math, time
import httpx

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db"
F_SET = DB / "settings.json"
F_OPEN = DB / "trades_open.json"
F_CLOSED = DB / "trades_closed.json"
F_SUM = DB / "trades_summary.json"

def _rj(p: Path, default):
    if not p.exists(): return default
    try:
        with p.open("r", encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def _wj(p: Path, data):
    with p.open("w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _binance_interval(tf: str) -> str:
    return tf if tf in {"1m","5m","15m"} else "1m"

async def _fetch_klines_async(symbol: str, tf: str, limit: int = 80):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": _binance_interval(tf), "limit": limit}
    async with httpx.AsyncClient(timeout=10.0) as cli:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        # close price = [4]
        return [float(x[4]) for x in data]

def _sma(xs, n):
    if len(xs) < n: return None
    return sum(xs[-n:]) / n

def _signal(prices):
    # SMA20/60 пересечение
    if len(prices) < 60: return None
    s20_prev = sum(prices[-21:-1])/20
    s60_prev = sum(prices[-61:-1])/60
    s20 = sum(prices[-20:])/20
    s60 = sum(prices[-60:])/60
    if s20_prev <= s60_prev and s20 > s60: return "BUY"
    if s20_prev >= s60_prev and s20 < s60: return "SELL"
    return None

def _current_exposure(open_trades):
    return sum(float(t.get("notional_usdc",0.0)) for t in open_trades)

def _qty_from_notional(notional, price):
    return round(notional/price, 8)

def _apply_pnl_to_summary(sumfile, pnl):
    sumfile["realized_pnl_usdc_total"] = round(sumfile.get("realized_pnl_usdc_total",0.0) + pnl, 6)
    # реинвест
    reinv = float(sumfile.get("reinvest_profit_pct", 0.0))
    adj = sumfile.get("adjustment_usdc", 0.0)
    if pnl > 0:
        adj += pnl * (reinv/100.0)
    else:
        adj += pnl  # убыток уменьшает корректировку
    sumfile["adjustment_usdc"] = round(adj, 6)
    sumfile["effective_max_usdc_exposure"] = round(sumfile.get("base_exposure_usdc",0.0) + adj, 6)

def run_tick():
    # загрузка данных
    settings = _rj(F_SET, {})
    if not settings:
        return {"processed":0,"opened":0,"closed":0,"errors":["no settings"]}

    if settings.get("trade_mode","paper") != "paper":
        return {"processed":0,"opened":0,"closed":0,"errors":["mode is not paper"]}

    symbols = settings.get("allowed_symbols", [])
    if not symbols:
        return {"processed":0,"opened":0,"closed":0,"errors":["no symbols"]}

    tf = settings.get("timeframe","1m")
    max_open = int(settings.get("max_open_positions",1))
    base_limit = float(settings.get("max_usdc_exposure",100.0))
    pos_cap = float(settings.get("max_position_size_usdc",25.0))
    risk_pct = float(settings.get("risk_per_trade_pct",0.5))  # пока не используется детально

    open_trades = _rj(F_OPEN, [])
    closed_trades = _rj(F_CLOSED, [])
    summary = _rj(F_SUM, {
        "open_count": 0, "closed_count": 0,
        "realized_pnl_usdc_total": 0.0, "realized_pnl_usdc_today": 0.0,
        "win_rate": 0.0, "avg_pnl_usdc": 0.0, "max_drawdown_usdc": 0.0,
        "base_exposure_usdc": base_limit, "adjustment_usdc": 0.0,
        "effective_max_usdc_exposure": base_limit, "reinvest_profit_pct": float(settings.get("reinvest_profit_pct",0.0))
    })

    opened = 0; closed = 0; errors = []
    import asyncio
    async def process_symbol(sym):
        try:
            prices = await _fetch_klines_async(sym, tf, 80)
        except Exception as e:
            errors.append(f"{sym}: {e}")
            return None
        sig = _signal(prices)
        price = float(prices[-1])
        return (sym, sig, price)

    # Параллельно тянем цены
    results = asyncio.run(asyncio.gather(*[process_symbol(s) for s in symbols]))
    # Индекс открытых по символу
    open_by_symbol = {t["symbol"]: t for t in open_trades}
    exposure_now = _current_exposure(open_trades)
    eff_limit = float(summary.get("effective_max_usdc_exposure", base_limit))

    for item in results:
        if not item: continue
        sym, sig, price = item
        if sig is None: continue

        has_open = sym in open_by_symbol
        # SELL — закрыть, если есть
        if sig == "SELL" and has_open:
            t = open_by_symbol[sym]
            qty = float(t["qty"])
            entry = float(t["entry_price"])
            side = t.get("side","BUY")
            # допустим только long BUY → закрытие по SELL
            if side == "BUY":
                pnl = (price - entry) * qty
                closed_trades.insert(0, {
                    "id": t["id"], "symbol": sym, "side": "BUY", "qty": qty,
                    "entry_price": entry, "exit_price": price,
                    "notional_usdc": t["notional_usdc"],
                    "pnl_usdc": round(pnl, 6),
                    "pnl_pct": round((pnl / max(1e-9, t["notional_usdc"])) * 100.0, 4),
                    "entry_time": t["entry_time"], "exit_time": _now_iso(),
                    "duration_sec": (datetime.fromisoformat(_now_iso()) - datetime.fromisoformat(t["entry_time"])).total_seconds()
                })
                open_trades = [x for x in open_trades if x["symbol"] != sym]
                open_by_symbol.pop(sym, None)
                exposure_now = _current_exposure(open_trades)
                _apply_pnl_to_summary(summary, pnl)
                closed += 1
            continue

        # BUY — открыть, если нет и хватает лимитов
        if sig == "BUY" and not has_open:
            if len(open_trades) >= max_open:
                continue
            remaining = eff_limit - exposure_now
            if remaining <= 1e-6:
                continue
            notional = float(min(pos_cap, remaining))
            qty = _qty_from_notional(notional, price)
            trade = {
                "id": f"T{int(time.time()*1000)}", "symbol": sym, "side": "BUY",
                "qty": qty, "entry_price": price, "notional_usdc": notional,
                "entry_time": _now_iso()
            }
            open_trades.append(trade)
            open_by_symbol[sym] = trade
            exposure_now = _current_exposure(open_trades)
            opened += 1

    # обновляем сводку
    summary["open_count"] = len(open_trades)
    summary["closed_count"] = len(closed_trades)
    # win-rate/avg pnl (по закрытым)
    if closed_trades:
        wins = sum(1 for t in closed_trades if t["pnl_usdc"] > 0)
        summary["win_rate"] = round(100.0 * wins / len(closed_trades), 2)
        summary["avg_pnl_usdc"] = round(sum(t["pnl_usdc"] for t in closed_trades) / len(closed_trades), 6)
    summary["last_tick_ts"] = _now_iso()

    _wj(F_OPEN, open_trades)
    _wj(F_CLOSED, closed_trades)
    _wj(F_SUM, summary)

    return {
        "processed": len(symbols),
        "opened": opened,
        "closed": closed,
        "errors": errors,
        "effective_limit": summary["effective_max_usdc_exposure"],
        "open_now": len(open_trades),
        "last_tick_ts": summary["last_tick_ts"]
    }
