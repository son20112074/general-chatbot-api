from typing import Optional
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Use Optional for fields that might not be set
    API_KEY: Optional[str] = None
    API_SECRET: Optional[str] = None
    BASE_URL: Optional[str] = 'http://localhost:8000/api/v1'
    REDIS_URL: Optional[str] = "redis://localhost:6379"

    LOG_LEVEL: str = "INFO"    
    
    # Database settings
    DATABASE_URI: PostgresDsn = "postgresql+asyncpg://postgres:123456@localhost:5433/tms"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 25
    DB_MAX_OVERFLOW: int = 40
    DB_SCHEMA: str = "public"

    # JWT settings
    SECRET_KEY: str = "4404229d1f3b6470a1b55b791dadb7035c9be77ac2d8dafcf9b25ff76cea8cef"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours (increased from 30 minutes)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 days (increased from 7 days)

    LLM_API: str = "https://api.openai.com/v1"

    # PaddleOCR-VL: optional vLLM server URL (e.g. ngrok). If set, image parser uses this instead of local model.
    PADDLEOCR_VL_SERVER_URL: Optional[str] = None

    # Content processing limits
    CONTENT_LIMIT: int = 20000  # Maximum content length for API processing

    # Add these settings to your Settings class
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_CELERY_DB: int = 1
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }

settings = Settings()

# settings.BASE_URL='http://localhost:8000/api/v1'
# settings.DATABASE_URI="postgresql+asyncpg://postgres:123456@localhost:5433/tms"

# settings.BASE_URL='http://192.168.1.90:8000/api/v1'
# settings.DATABASE_URI="postgresql+asyncpg://postgres:123456@localhost:5432/tms"