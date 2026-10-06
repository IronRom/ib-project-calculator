from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://pir_user:pir_password@db:5432/pir_calc"
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days
    admin_email: str = "admin@localhost"
    admin_password: str = "Admin12345!"
    uploads_dir: str = "/app/uploads"
    extraction_model: str = "claude-sonnet-4-6"
    # OpenRouter-модель для vision-OCR сканов (document_parser._parse_pdf_vision).
    # Только ДЕФОЛТ: рабочее значение — app_settings.ocr_model (админка).
    ocr_model: str = "google/gemini-3.6-flash"
    max_tz_chars: int = 50_000
    # Потолок каталога типов объектов в промпте Pass 1, когда справочники
    # НЕ определены (fallback). Полный каталог активных книг — ~470 тыс.
    # символов (~180 тыс. токенов): это и дорого, и вредно для качества —
    # модель выбирает из сотни книг. Берём релевантные ТЗ в пределах лимита.
    max_catalog_chars: int = 120_000
    # ── Telegram-бот ──────────────────────────────────────────────────────
    # Общий секрет между ботом и backend для привилегированных вызовов
    # (/auth/telegram/link, /auth/telegram/resolve). Бот шлёт его в заголовке
    # X-Bot-Secret; со стороны интернета эти ручки без секрета недоступны.
    bot_api_secret: str = ""
    # @username бота — нужен для deep-link из кабинета (t.me/<username>?start=)
    telegram_bot_username: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
