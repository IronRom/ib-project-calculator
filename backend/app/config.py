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

    class Config:
        env_file = ".env"


settings = Settings()
