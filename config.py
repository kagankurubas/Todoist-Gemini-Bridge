import os
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application configuration and environment variable validation."""

    TODOIST_API_TOKEN: str = Field(
        ...,
        description="Todoist API token for authenticating REST requests",
    )
    WEBHOOK_SECRET_TOKEN: str = Field(
        ...,
        description="Secret token for authenticating incoming webhooks / API requests",
    )
    ALLOWED_ORIGINS: str = Field(
        default="*",
        description="Allowed CORS origins comma-separated or * for all origins",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Global settings instance
settings = Settings()
