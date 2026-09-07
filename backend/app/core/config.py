import json
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "ProjectSynapse"
    APP_ENV: str = "development"
    API_V1_STR: str = "/api/v1"
    
    # Primary Target: PostgreSQL with pgvector
    # Fallback: SQLite local file (sqlite+aiosqlite:///./project_synapse.db)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/project_synapse"

    # AI Provider: 'mock' (default, offline), 'gemini', 'openai', 'ollama'
    AI_PROVIDER: str = "mock"
    GEMINI_API_KEY: Union[str, None] = None
    OPENAI_API_KEY: Union[str, None] = None

    # CORS settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, str) and v.startswith("["):
            return json.loads(v)
        return v


settings = Settings()
