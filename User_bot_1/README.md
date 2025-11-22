# Trustat alert forwarder

Этот бот слушает сообщения из канала-источника (например, `@TrustatAlertsBot`), находит в них ссылки `t.me/...`, открывает каждую ссылку, загружает исходное сообщение и пересылает его в указанные целевые каналы. Сообщения ставятся в очередь с учётом ограничений Telegram, а каждая ссылка обрабатывается только один раз.

## Быстрый запуск

1. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

2. Создайте файл `.env` рядом с `run.py` и заполните его настройками Telegram (бот работает от имени пользовательского аккаунта, не бот-токена). Авторизация выполняется только через строку сессии `TELEGRAM_STRING_SESSION`, полученную заранее. Пример файла:

   ```env
   TELEGRAM_API_ID=31847442
   TELEGRAM_API_HASH=365488c19dfc94489f4628436f2fdd92
   TELEGRAM_STRING_SESSION=<сюда вставьте строку сессии>
   SOURCE_CHANNEL=@neoalertstest
   TARGET_CHANNELS=@test_neouser
   FORWARDING_ENABLED=true
   FORWARDING_MAX_MESSAGES_PER_SECOND=1.0
   FORWARDING_QUEUE_MAXSIZE=100
   FORWARDING_DELAY_SECONDS=1.5
   DB_URL=sqlite+aiosqlite:///db.sqlite3
   LOG_LEVEL=INFO
   ```

   - `TARGET_CHANNELS` принимает список через запятую.
   - `FORWARDING_ENABLED=false` включает режим «сухого прогона» без отправки сообщений.

3. Запустите бота:

   ```bash
   # при необходимости получите строку сессии (разовый интерактивный вход):
   python create_session.py

   # затем запустите основного бота
   python run.py
   ```


Бот использует только строковую сессию `TELEGRAM_STRING_SESSION` и ведёт базу данных для проверки уникальности сообщений.

## Поведение

- Новые сообщения из `SOURCE_CHANNEL` сканируются на наличие ссылок вида `https://t.me/<channel>/<id>` или `https://t.me/c/<id>/<msg_id>`.
- Каждая ссылка ставится в очередь. Очередь уважает задержку `FORWARDING_DELAY_SECONDS` и ограничение `FORWARDING_MAX_MESSAGES_PER_SECOND`.
- Перед отправкой бот загружает исходное сообщение по ссылке и пересылает его в каждый канал из `TARGET_CHANNELS`.
- Все ссылки и сообщения помечаются в SQLite-базе, чтобы не пересылать одно и то же повторно.
