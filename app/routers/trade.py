from fastapi import APIRouter, HTTPException, Depends
from app.models import PreviewRequest, PreviewResponse, MarketOrderRequest, Settings
from app.utils.storage import load_settings
from app.utils.auth import require_bearer
from app.config import config

router = APIRouter()

# Простейший расчёт размера позиции (MVP, paper-логика)
@router.post("/trade/preview", response_model=PreviewResponse)
def trade_preview(req: PreviewRequest):
    s: Settings = load_settings()
    # оценка цены: если не задана — считаем как 1.0 для примера (в проде получить реальную цену из /ticker)
    price = req.price or 1.0
    # ограничение позиции
    qty_by_pos = s.max_position_size_usdc / max(price, 1e-8)
    # экспозиция — здесь упростим, рассчитываем только текущую сделку
    est_cost = qty_by_pos * price
    stop_price = price * (1 - req.stop_distance_pct / 100) if req.side == "BUY" else price * (1 + req.stop_distance_pct / 100)
    take_price = price * (1 + req.take_profit_pct / 100) if req.side == "BUY" else price * (1 - req.take_profit_pct / 100)
    return PreviewResponse(
        symbol=req.symbol.upper(),
        side=req.side,
        qty=round(qty_by_pos, 8),
        est_cost_usdc=round(est_cost, 2),
        stop_price=round(stop_price, 8),
        take_profit_price=round(take_price, 8),
        notes="MVP preview without live price feed"
    )

@router.post("/trade/market")
def trade_market(req: MarketOrderRequest, _: bool = Depends(require_bearer)):
    s: Settings = load_settings()
    if config.trade_mode != "paper" or config.live_enabled:
        # TODO: здесь разместить реальный ордер на Binance (SIGNED /api/v3/order)
        pass
    # В режиме paper — просто возвращаем симулированный ответ
    qty = req.qty
    if qty is None:
        price = 1.0  # TODO: получить реальную цену
        qty = s.max_position_size_usdc / max(price, 1e-8)
    return {
        "paper": True,
        "symbol": req.symbol.upper(),
        "side": req.side,
        "qty": round(qty, 8),
        "return_to_usdc_on_close": req.return_to_usdc_on_close if req.return_to_usdc_on_close is not None else s.return_to_usdc,
        "message": "Order simulated (paper mode). For LIVE set LIVE_ENABLED=true and TRADE_MODE=live."
    }
