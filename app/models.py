from pydantic import BaseModel, Field, validator
from typing import List, Literal, Optional

TradeMode = Literal["paper", "live"]

class Settings(BaseModel):
    trade_mode: TradeMode = "paper"
    max_usdc_exposure: float = Field(100.0, ge=0, description="Макс. совокупная экспозиция в USDC")
    max_position_size_usdc: float = Field(25.0, ge=0, description="Макс. размер одной позиции в USDC")
    max_open_positions: int = Field(1, ge=0, description="Макс. число одновременно открытых позиций")
    risk_per_trade_pct: float = Field(0.5, ge=0, le=100, description="Риск на сделку, % от депозита")
    max_daily_loss_usdc: float = Field(25.0, ge=0, description="Дневной лимит потерь в USDC")
    return_to_usdc: bool = True
    news_pause_enabled: bool = True
    allowed_symbols: List[str] = []

    @validator("allowed_symbols", pre=True)
    def norm_syms(cls, v):
        return [s.upper() for s in v] if v else []
    
class PreviewRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    price: Optional[float] = None  # если нет — возьмём рыночную цену
    stop_distance_pct: float = Field(1.0, gt=0, description="Дистанция стопа в %")
    take_profit_pct: float = Field(1.0, gt=0, description="Тейк профит в %")

class PreviewResponse(BaseModel):
    symbol: str
    side: str
    qty: float
    est_cost_usdc: float
    stop_price: float | None = None
    take_profit_price: float | None = None
    notes: str | None = None

class MarketOrderRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: float | None = None  # если None — рассчитаем сами из настроек
    return_to_usdc_on_close: bool | None = None  # override глобальной настройки
