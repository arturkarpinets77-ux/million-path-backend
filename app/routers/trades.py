# app/routers/trades.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from ..core.storage import load_json, save_json
from .settings import SETTINGS_FILE, STATE_FILE, SettingsModel, _read_state, _write_state, _compute_effective

router = APIRouter(tags=["trades"])

OPEN_FILE = "open_trades.json"
CLOSED_FILE = "closed_trades.json"

class TradeOpen(BaseModel):
    id: str
    symbol: str
    side: str                # BUY / SELL
    qty: float
    entry_price: float
    notional_usdc: float
    entry_time: str          # ISO8601

class TradeClosed(BaseModel):
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    pnl_usdc: float
    pnl_pct: float
    entry_time: str
    exit_time: str
    duration_sec: float

class TradesSummary(BaseModel):
    open_count: int
    closed_count: int
    realized_pnl_usdc_total: float
    realized_pnl_usdc_today: float
    win_rate: float
    avg_pnl_usdc: float
    max_drawdown_usdc: float
    base_exposure_usdc: float
    adjustment_usdc: float
    effective_max_usdc_exposure: float
    reinvest_profit_pct: float

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _load_list(name: str) -> List[Dict[str, Any]]:
    return load_json(name, [])

def _save_list(name: str, data: List[Dict[str, Any]]) -> None:
    save_json(name, data)

def _load_settings() -> SettingsModel:
    raw = load_json(SETTINGS_FILE, {})
    return SettingsModel(**raw)

@router.get("/trades/open", response_model=List[TradeOpen])
async def get_open():
    return _load_list(OPEN_FILE)

@router.get("/trades/closed", response_model=List[TradeClosed])
async def get_closed(limit: int = 200):
    lst = _load_list(CLOSED_FILE)
    lst.sort(key=lambda x: x.get("exit_time",""), reverse=True)
    return lst[: max(1, min(limit, 1000))]

@router.get("/trades/summary", response_model=TradesSummary)
async def get_summary():
    open_tr = _load_list(OPEN_FILE)
    closed_tr = _load_list(CLOSED_FILE)
    s = _load_settings()
    st = _read_state()

    total = sum(float(x.get("pnl_usdc", 0.0)) for x in closed_tr)
    # pnl сегодня (UTC по дате закрытия)
    today = datetime.now(timezone.utc).date()
    today_pnl = 0.0
    wins = 0
    for x in closed_tr:
        try:
            dt = datetime.fromisoformat(x.get("exit_time"))
            if dt.date() == today:
                today_pnl += float(x.get("pnl_usdc", 0.0))
        except Exception:
            pass
        if float(x.get("pnl_usdc", 0.0)) > 0:
            wins += 1

    win_rate = (wins / len(closed_tr)) * 100.0 if closed_tr else 0.0
    avg_pnl = (total / len(closed_tr)) if closed_tr else 0.0

    # простая оценка max drawdown по кум. кривой
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in closed_tr:
        cum += float(x.get("pnl_usdc", 0.0))
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    eff = _compute_effective(s, st)
    return TradesSummary(
        open_count=len(open_tr),
        closed_count=len(closed_tr),
        realized_pnl_usdc_total=round(total, 8),
        realized_pnl_usdc_today=round(today_pnl, 8),
        win_rate=round(win_rate, 2),
        avg_pnl_usdc=round(avg_pnl, 8),
        max_drawdown_usdc=round(max_dd, 8),
        base_exposure_usdc=s.max_usdc_exposure,
        adjustment_usdc=float(st.get("exposure_adjustment_usdc", 0.0)),
        effective_max_usdc_exposure=eff,
        reinvest_profit_pct=s.reinvest_profit_pct
    )

# ---- Ниже 2 endpoint'а для записи/закрытия сделок (чтобы можно было тестировать) ----

class PostOpen(BaseModel):
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    notional_usdc: float
    entry_time: Optional[str] = None

@router.post("/trades/open", response_model=TradeOpen)
async def post_open(p: PostOpen):
    o = p.dict()
    if not o.get("entry_time"):
        o["entry_time"] = _utcnow_iso()
    open_tr = _load_list(OPEN_FILE)
    if any(x.get("id")==o["id"] for x in open_tr):
        raise HTTPException(400, "id already exists")
    open_tr.append(o)
    _save_list(OPEN_FILE, open_tr)
    return o

class PostClose(BaseModel):
    id: str
    exit_price: float
    exit_time: Optional[str] = None

@router.post("/trades/close", response_model=TradeClosed)
async def post_close(p: PostClose):
    open_tr = _load_list(OPEN_FILE)
    idx = next((i for i,x in enumerate(open_tr) if x.get("id")==p.id), None)
    if idx is None:
        raise HTTPException(404, "open trade not found")
    o = open_tr.pop(idx)
    _save_list(OPEN_FILE, open_tr)

    # формируем закрытую
    exit_time = p.exit_time or _utcnow_iso()
    qty = float(o["qty"])
    entry = float(o["entry_price"])
    exitp = float(p.exit_price)
    side = o["side"].upper()
    # PnL по направлению
    diff = (exitp - entry) if side=="BUY" else (entry - exitp)
    pnl_usdc = diff * qty
    pnl_pct = (diff / entry) * 100.0 if entry else 0.0

    c = {
        "id": o["id"], "symbol": o["symbol"], "side": side, "qty": qty,
        "entry_price": entry, "exit_price": exitp,
        "pnl_usdc": pnl_usdc, "pnl_pct": pnl_pct,
        "entry_time": o["entry_time"], "exit_time": exit_time,
        "duration_sec": max(0.0, (datetime.fromisoformat(exit_time) - datetime.fromisoformat(o["entry_time"])).total_seconds())
    }
    closed_tr = _load_list(CLOSED_FILE)
    closed_tr.append(c)
    _save_list(CLOSED_FILE, closed_tr)

    # авто-коррекция экспозиции
    s = _load_settings()
    st = _read_state()
    adj = float(st.get("exposure_adjustment_usdc", 0.0))
    if s.auto_adjust_exposure:
        if pnl_usdc > 0:
            adj += pnl_usdc * (float(s.reinvest_profit_pct)/100.0)
        else:
            adj += pnl_usdc  # убыток вычитаем полностью (отрицательное число)
        st["exposure_adjustment_usdc"] = adj
        st["realized_pnl_total_usdc"] = float(st.get("realized_pnl_total_usdc", 0.0)) + pnl_usdc
        _write_state(st)

    return c
