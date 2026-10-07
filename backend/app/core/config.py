"""Application configuration using Pydantic Settings."""
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_ENV: str = "development"
    DEMO_MODE: bool = True
    SECRET_KEY: str = "sentinelops_super_secret_jwt_key_hackathon_2026_demo_random_32_chars"
    ACCESS_TOKEN_MINUTES: int = 1440
    DATABASE_URL: str = "sqlite:///./sentinelops.db"
    CORS_ORIGINS: Union[str, List[str]] = "*"
    FRONTEND_URL: str = "http://localhost:5173"

    # AI Configuration
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GROQ_API_KEY: str = ""

    # Notifications
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""

    # Storage Backend
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_BUCKET: str = "evidence"
    STORAGE_BACKEND: str = "local"

    # Integrations & Geofencing
    IOT_API_KEY: str = "sentinel_iot_key_secret_104"
    AVG_SPEED_KMH: float = 40.0
    GEOFENCE_DEFAULT_M: float = 500.0

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v == "*":
                return ["*"]
            return [i.strip() for i in v.split(",") if i.strip()]
        return v


settings = Settings()
