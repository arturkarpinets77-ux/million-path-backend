from fastapi import FastAPI
from app.routers import health, market, settings, trade

app = FastAPI(title="Million Path Backend", version="0.1.0")

app.include_router(health.router)
app.include_router(market.router)
app.include_router(settings.router)
app.include_router(trade.router)

# Технический тик-эндпоинт (можно вызывать cron-ом)
@app.post("/tick")
def tick():
    # TODO: добавить анализ по списку символов, генерацию сигналов, пуш-уведомления
    return {"ok": True, "note": "tick placeholder"}
