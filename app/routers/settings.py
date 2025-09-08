from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json, os
from datetime import datetime, timezone

router = APIRouter(prefix="/settings", tags=["settings"])

ROOT = Path(__file__).resolve().parents[1]  # .../app
DB = ROOT / "db"
DB.mkdir(exist_ok=True)

F_SET = DB / "settings.json"
F_SUM = DB / "trades_summary.json"

def _read_json(p: Path, default):
    if not p.exists(): return default
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _write_json(p: Path, data):
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _auth_ok(authorization: str | None) -> bool:
    if not authorization: return False
    if not authorization.lower().startswith("bearer "): return False
    token = authorization.split(" ", 1)[1]
    expected = os.getenv("APP_TOKEN", "MySecret123")
    return token == expected

class SettingsModel(BaseModel):
    trade_mode: str = "paper"
    max_usdc_exposure: float = 100.0
    max_position_size_usdc: float = 25.0
    max_open_positions: int = 1
    risk_per_trade_pct: float = 0.5
    max_daily_loss_usdc: float = 25.0
    return_to_usdc: bool = True
    news_pause_enabled: bool = True
    allowed_symbols: list[str] = []
    reinvest_profit_pct: float = 0.0
    auto_adjust_exposure: bool = True
    # вычисляемое поле — вернём клиенту для удобства
    effective_max_usdc_exposure: float | None = None

def _effective_exposure(base: float) -> float:
    sumfile = _read_json(F_SUM, {})
    adj = float(sumfile.get("adjustment_usdc", 0.0))
    return round(float(base) + adj, 6)

@router.get("")
def get_settings(authorization: str | None = Header(default=None)):
    if not _auth_ok(authorization): raise HTTPException(401)
    raw = _read_json(F_SET, {})
    s = SettingsModel(**{
        "trade_mode": raw.get("trade_mode", "paper"),
        "max_usdc_exposure": raw.get("max_usdc_exposure", 100.0),
        "max_position_size_usdc": raw.get("max_position_size_usdc", 25.0),
        "max_open_positions": raw.get("max_open_positions", 1),
        "risk_per_trade_pct": raw.get("risk_per_trade_pct", 0.5),
        "max_daily_loss_usdc": raw.get("max_daily_loss_usdc", 25.0),
        "return_to_usdc": raw.get("return_to_usdc", True),
        "news_pause_enabled": raw.get("news_pause_enabled", True),
        "allowed_symbols": raw.get("allowed_symbols", []),
        "reinvest_profit_pct": raw.get("reinvest_profit_pct", 0.0),
        "auto_adjust_exposure": raw.get("auto_adjust_exposure", True),
        "effective_max_usdc_exposure": _effective_exposure(raw.get("max_usdc_exposure", 100.0)),
    })
    return s

@router.put("")
def put_settings(body: SettingsModel, authorization: str | None = Header(default=None)):
    if not _auth_ok(authorization): raise HTTPException(401)
    # сохраняем настройки
    out = body.dict()
    out.pop("effective_max_usdc_exposure", None)
    _write_json(F_SET, out)

    # синхронизируем сводку (базовый лимит и % реинвеста)
    sumfile = _read_json(F_SUM, {
        "open_count": 0, "closed_count": 0,
        "realized_pnl_usdc_total": 0.0, "realized_pnl_usdc_today": 0.0,
        "win_rate": 0.0, "avg_pnl_usdc": 0.0,
        "max_drawdown_usdc": 0.0,
        "base_exposure_usdc": body.max_usdc_exposure,
        "adjustment_usdc": 0.0,
        "effective_max_usdc_exposure": body.max_usdc_exposure,
        "reinvest_profit_pct": body.reinvest_profit_pct,
        "today": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    })
    sumfile["base_exposure_usdc"] = float(body.max_usdc_exposure)
    sumfile["reinvest_profit_pct"] = float(body.reinvest_profit_pct)
    sumfile["effective_max_usdc_exposure"] = _effective_exposure(body.max_usdc_exposure)
    _write_json(F_SUM, sumfile)

    # вернём обратно с просчитанным effective
    out["effective_max_usdc_exposure"] = sumfile["effective_max_usdc_exposure"]
    return out
