from pydantic import BaseModel
import os

class AppConfig(BaseModel):
    app_token: str | None = os.getenv("APP_TOKEN")
    trade_mode: str = os.getenv("TRADE_MODE", "paper")  # paper | live
    quote_asset: str = os.getenv("QUOTE_ASSET", "USDC")
    binance_key: str | None = os.getenv("BINANCE_KEY")
    binance_secret: str | None = os.getenv("BINANCE_SECRET")
    live_enabled: bool = os.getenv("LIVE_ENABLED", "false").lower() == "true"

config = AppConfig()
