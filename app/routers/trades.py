from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json, time, os
from datetime import datetime, timezone

router = APIRouter(prefix="/trades", tags=["trades"])

# ---- storage helpers
ROOT = Path(__file__).resolve().parents[1]  # .../app
DB = ROOT / "db"
DB.mkdir(exist_ok=True)

F_OPEN   = DB / "trades_open.json"
F_CLOSED = DB / "trades_closed.json"
F_SUM    = DB / "trades_summary.json"
F_SET    = DB / "settings.json"

def _read_json(p: Path, default):
    if not p.exists():
        return default
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _write_json(p: Path, data):
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _today_str(dt: datetime | None = None):
    d = dt or datetime.now(timezone.utc)
    return d.strftime("%Y-%m-%d")

# ---- auth
def _auth_ok(authorization: str | None) -> bool:
    if not authorization: 
        return False
    if not authorization.lower().startswith("bearer "):
        return False
    token = authorization.split(" ", 1)[1]
    expected = os.getenv("APP_TOKEN", "MySecret123")
    return token == expected

# ---- models
class PostOpen(BaseModel):
    id: str
    symbol: str
    side: str        # BUY / SELL
    qty: float
    entry_price: float
    notional_usdc: float

class PostClose(BaseModel):
    id: str
    exit_price: float

# ---- helpers for settings/exposure
def _load_settings():
    s = _read_json(F_SET, {})
    # sane defaults
    s.setdefault("max_usdc_exposure", 100.0)
    s.setdefault("reinvest_profit_pct", 0.0)
    s.setdefault("auto_adjust_exposure", True)
    return s

def _load_summary_default():
    s = _load_settings()
    return {
        "open_count": 0,
        "closed_count": 0,
        "realized_pnl_usdc_total": 0.0,
        "realized_pnl_usdc_today": 0.0,
        "win_rate": 0.0,
        "avg_pnl_usdc": 0.0,
        "max_drawdown_usdc": 0.0,
        "base_exposure_usdc": s["max_usdc_exposure"],
        "adjustment_usdc": 0.0,
        "effective_max_usdc_exposure": s["max_usdc_exposure"],
        "reinvest_profit_pct": s["reinvest_profit_pct"],
        "today": _today_str(),
    }

def _recalc_summary(open_list, closed_list):
    s = _read_json(F_SUM, _load_summary_default())
    # базовые из настроек (могли измениться)
    sets = _load_settings()
    s["base_exposure_usdc"] = sets["max_usdc_exposure"]
    s["reinvest_profit_pct"] = sets["reinvest_profit_pct"]

    s["open_count"] = len(open_list)
    s["closed_count"] = len(closed_list)

    total = sum(x.get("pnl_usdc", 0.0) for x in closed_list)
    s["realized_pnl_usdc_total"] = round(total, 6)

    today = _today_str()
    s["realized_pnl_usdc_today"] = round(
        sum(x.get("pnl_usdc", 0.0) for x in closed_list if x.get("exit_time","")[:10] == today), 6
    )

    wins = sum(1 for x in closed_list if x.get("pnl_usdc", 0.0) > 0)
    s["win_rate"] = round(100.0 * wins / max(1, len(closed_list)), 2)

    s["avg_pnl_usdc"] = round(total / max(1, len(closed_list)), 6)

    # max drawdown: упрощённо — минимальная накопленная кумулятивная доходность
    cum, min_cum = 0.0, 0.0
    for x in closed_list:
        cum += x.get("pnl_usdc", 0.0)
        min_cum = min(min_cum, cum)
    s["max_drawdown_usdc"] = round(-min_cum, 6)

    s["effective_max_usdc_exposure"] = round(s["base_exposure_usdc"] + s["adjustment_usdc"], 6)

    _write_json(F_SUM, s)
    return s

# ---- GET endpoints
@router.get("/open")
def get_open_trades(authorization: str | None = Header(default=None)):
    if not _auth_ok(authorization): raise HTTPException(401)
    return _read_json(F_OPEN, [])

@router.get("/closed")
def get_closed_trades(limit: int = 200, authorization: str | None = Header(default=None)):
    if not _auth_ok(authorization): raise HTTPException(401)
    arr = _read_json(F_CLOSED, [])
    return arr[-limit:]

@router.get("/summary")
def get_summary(authorization: str | None = Header(default=None)):
    if not _auth_ok(authorization): raise HTTPException(401)
    open_list = _read_json(F_OPEN, [])
    closed_list = _read_json(F_CLOSED, [])
    return _recalc_summary(open_list, closed_list)

# ---- POST open/close
@router.post("/open")
def post_open(body: PostOpen, authorization: str | None = Header(default=None)):
    if not _auth_ok(authorization): raise HTTPException(401)
    open_list = _read_json(F_OPEN, [])
    # forbid duplicate IDs
    if any(x["id"] == body.id for x in open_list):
        raise HTTPException(400, detail="id already open")
    now = _now_iso()
    row = {
        "id": body.id,
        "symbol": body.symbol.upper(),
        "side": body.side.upper(),
        "qty": float(body.qty),
        "entry_price": float(body.entry_price),
        "notional_usdc": float(body.notional_usdc),
        "entry_time": now
    }
    open_list.append(row)
    _write_json(F_OPEN, open_list)
    # update summary counters (open_count)
    _recalc_summary(open_list, _read_json(F_CLOSED, []))
    return row

@router.post("/close")
def post_close(body: PostClose, authorization: str | None = Header(default=None)):
    if not _auth_ok(authorization): raise HTTPException(401)
    open_list = _read_json(F_OPEN, [])
    idx = next((i for i,x in enumerate(open_list) if x["id"] == body.id), None)
    if idx is None:
        raise HTTPException(404, detail="id not found")
    row = open_list.pop(idx)
    exit_time = _now_iso()
    side = row["side"]
    qty = float(row["qty"])
    entry = float(row["entry_price"])
    exitp = float(body.exit_price)

    # pnl BUY = q*(exit-entry); SELL = q*(entry-exit)
    pnl = qty * (exitp - entry) if side == "BUY" else qty * (entry - exitp)
    pnl_pct = 0.0
    if row["notional_usdc"] > 0:
        pnl_pct = 100.0 * pnl / float(row["notional_usdc"])

    closed_row = {
        **row,
        "exit_price": exitp,
        "pnl_usdc": round(pnl, 6),
        "pnl_pct": round(pnl_pct, 4),
        "exit_time": exit_time,
        "duration_sec": round(
            max(0.0, datetime.fromisoformat(exit_time).timestamp() - datetime.fromisoformat(row["entry_time"]).timestamp()), 3
        )
    }
    closed_list = _read_json(F_CLOSED, [])
    closed_list.append(closed_row)
    _write_json(F_OPEN, open_list)
    _write_json(F_CLOSED, closed_list)

    # adjust exposure if enabled
    summary = _read_json(F_SUM, _load_summary_default())
    sets = _load_settings()
    if sets.get("auto_adjust_exposure", True):
        if pnl >= 0:
            k = float(sets.get("reinvest_profit_pct", 0.0)) / 100.0
            summary["adjustment_usdc"] = round(float(summary.get("adjustment_usdc", 0.0)) + pnl * k, 6)
        else:
            summary["adjustment_usdc"] = round(float(summary.get("adjustment_usdc", 0.0)) + pnl, 6)  # pnl < 0

    _write_json(F_SUM, summary)
    _recalc_summary(open_list, closed_list)
    return closed_row

# ---- RESET everything
@router.post("/reset")
def post_reset(authorization: str | None = Header(default=None)):
    if not _auth_ok(authorization): raise HTTPException(401)
    _write_json(F_OPEN, [])
    _write_json(F_CLOSED, [])
    _write_json(F_SUM, _load_summary_default())
    return {"ok": True, "note": "trades cleared"}
