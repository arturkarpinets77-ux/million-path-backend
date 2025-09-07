# Путь к миллиону — Backend (FastAPI, Render Free)

Минимальный бэкенд для крипто‑бота под пары с **USDC** на Binance.
Работает на бесплатном тарифе Render (спит без трафика).

## Быстрый старт (локально)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Открой: http://127.0.0.1:8000/health и http://127.0.0.1:8000/docs

## Деплой на Render (Hobby/Free)
1. Залей репозиторий в GitHub.
2. Create Web Service → выбрать **Free**.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. В **Environment** укажи переменные (см. ниже).

### Переменные окружения (пример)
- `APP_TOKEN` — токен для простейшей авторизации (Bearer).
- `TRADE_MODE` — `paper` или `live` (по умолчанию `paper`).
- `QUOTE_ASSET` — `USDC` (по умолчанию `USDC`).
- `BINANCE_KEY`, `BINANCE_SECRET` — для реальной торговли (опционально на MVP).
- `LIVE_ENABLED` — `false` (по умолчанию). Поставь `true`, если точно хочешь включить создание живых ордеров.

### Важно про Free
Сервис засыпает. Чтобы «будить» и/или запускать периодический тик, можно бесплатно пинговать
`GET /health` или `POST /tick` через внешний cron (например, cron-job.org).

## Эндпоинты (основные)
- `GET /health` — статус и аптайм.
- `GET /symbols/usdc` — список доступных спот‑пар с котировкой в USDC (по `exchangeInfo`).
- `GET /settings` — текущие торговые настройки.
- `PUT /settings` — изменить настройки (требуется Bearer токен).
- `POST /trade/preview` — расчёт объёма/риск‑профиля без размещения ордера.
- `POST /trade/market` — размещение MARKET‑ордера (в `paper` режиме — симуляция).
- `POST /tick` — разовый анализ/цикл (MVP-заглушка).

## Модель настроек (пример JSON)
```json
{
  "trade_mode": "paper",
  "max_usdc_exposure": 200.0,
  "max_position_size_usdc": 50.0,
  "max_open_positions": 2,
  "risk_per_trade_pct": 0.5,
  "max_daily_loss_usdc": 50.0,
  "return_to_usdc": true,
  "news_pause_enabled": true,
  "allowed_symbols": ["BTCUSDC", "ETHUSDC"]
}
```

## Безопасность
- Ключи Binance храним только на сервере (в переменных окружения).
- Простая авторизация через `APP_TOKEN` (Bearer) — достаточно для MVP. Позже можно перейти на JWT + роли.

## Лицензия
MIT
