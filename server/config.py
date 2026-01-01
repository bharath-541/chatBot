from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os

class Settings(BaseSettings):
    google_api_key: str
    google_maps_api_key: str = ""
    # Use absolute path for SQLite to avoid issues in different environments
    database_url: str = f"sqlite+aiosqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chatbot.db')}"
    host: str = "0.0.0.0"
    port: int = int(os.getenv("PORT", 8000))
    
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), '.env'),
        env_file_encoding='utf-8',
        case_sensitive=False
    )

@lru_cache()
def get_settings():
    return Settings()
