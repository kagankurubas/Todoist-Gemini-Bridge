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
        default="supersecret",
        description="Secret token for authenticating incoming webhooks / API requests",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Global settings instance
settings = Settings()
