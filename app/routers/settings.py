# app/routers/settings.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from ..core.storage import load_json, save_json

router = APIRouter(tags=["settings"])

SETTINGS_FILE = "settings.json"
STATE_FILE = "state.json"

class SettingsModel(BaseModel):
    trade_mode: str = "paper"
    max_usdc_exposure: float = 100.0          # БАЗОВЫЙ лимит (то, что вводишь руками)
    max_position_size_usdc: float = 25.0
    max_open_positions: int = 1
    risk_per_trade_pct: float = 0.5
    max_daily_loss_usdc: float = 25.0
    return_to_usdc: bool = True
    news_pause_enabled: bool = True
    allowed_symbols: List[str] = Field(default_factory=list)

    # новые поля авто-коррекции
    reinvest_profit_pct: float = 0.0          # % от чистой прибыли, добавляемый к лимиту
    auto_adjust_exposure: bool = True         # вычитать убыток и добавлять % прибыли

    # вычисляемое поле (только в ответе)
    effective_max_usdc_exposure: float = 0.0

def _read_state() -> Dict[str, Any]:
    st = load_json(STATE_FILE, {"exposure_adjustment_usdc": 0.0, "realized_pnl_total_usdc": 0.0})
    # совместимость/валидация
    st.setdefault("exposure_adjustment_usdc", 0.0)
    st.setdefault("realized_pnl_total_usdc", 0.0)
    return st

def _write_state(st: Dict[str, Any]) -> None:
    save_json(STATE_FILE, st)

def _compute_effective(settings: SettingsModel, state: Dict[str, Any]) -> float:
    if not settings.auto_adjust_exposure:
        return settings.max_usdc_exposure
    base = float(settings.max_usdc_exposure)
    adj = float(state.get("exposure_adjustment_usdc", 0.0))
    return max(0.0, base + adj)

@router.get("/settings", response_model=SettingsModel)
async def get_settings():
    raw = load_json(SETTINGS_FILE, {})
    s = SettingsModel(**raw)
    st = _read_state()
    s.effective_max_usdc_exposure = _compute_effective(s, st)
    return s

@router.put("/settings", response_model=SettingsModel)
async def update_settings(s: SettingsModel):
    # сохраняем как базовую конфигурацию (effective пересчитаем на лету)
    data = s.dict()
    data.pop("effective_max_usdc_exposure", None)
    save_json(SETTINGS_FILE, data)

    st = _read_state()
    s.effective_max_usdc_exposure = _compute_effective(s, st)
    return s
