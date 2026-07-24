import os


class Config:
    bot_token: str = os.environ["TELEGRAM_BOT_TOKEN"]
    # Внутренний адрес backend (в docker-сети — http://backend:8000)
    backend_url: str = os.environ.get("BACKEND_URL", "http://backend:8000").rstrip("/")
    # Общий секрет с backend для /auth/telegram/{link,resolve}
    bot_api_secret: str = os.environ.get("BOT_API_SECRET", "")
    # Максимальный размер файла ТЗ, который бот примет (лимит Telegram = 20 МБ)
    max_file_mb: int = int(os.environ.get("BOT_MAX_FILE_MB", "20"))
    # Тайминги фоновой обработки расчёта
    poll_interval_s: float = 4.0
    poll_timeout_s: float = 20 * 60


config = Config()
