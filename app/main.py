from fastapi import FastAPI
from app.routers import health, market, settings, trade
from app.services.tick import run_tick   # <— добавили

app = FastAPI(title="Million Path Backend", version="0.2.0")

app.include_router(health.router)
app.include_router(market.router)
app.include_router(settings.router)
app.include_router(trade.router)

# Технический тик-эндпоинт (один проход стратегии по списку символов)
@app.post("/tick")
def tick():
    result = run_tick()
    return {"ok": True, **result}
