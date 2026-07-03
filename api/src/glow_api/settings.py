import json
from typing import Any, List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


def parse_list(v: Any) -> List[str]:
    if isinstance(v, str):
        v = v.strip()
        if v.startswith("["):
            return json.loads(v)
        return [s.strip() for s in v.split(",") if s.strip()]
    return v


class Settings(BaseSettings):
    # ODK Central configuration
    ODK_API_URL: str = "http://localhost:8383"  # Default for testing
    ODK_API_EMAIL: str = "test@example.com"  # Default for testing
    ODK_API_PASSWORD: str = "test-password"  # Default for testing
    ODK_PROJECT_ID: int = 1  # Default for testing
    ODK_DEMOGRAPHICS_FORM_ID: str = "demographics_questionnaire"

    # Data refresh configuration
    DATA_CACHE_PATH: Optional[str] = None  # If set, cache DataFrame and ETAG
    DATA_REFRESH_HOURS: int = 1  # Poll ODK Central every hour
    DATA_PREFIXES: List[str] = ["bw", "phq9"]
    DATA_DEMOGRAPHIC_PREFIXES: List[str] = ["d"]

    # Period derivation configuration
    PERIOD_TIMEZONE: str = (
        "Europe/London"  # Deployment timezone for period calculations
    )
    PERIOD_CUTOFF_MONTH: int = 9  # September (academic year starts)
    PERIOD_CUTOFF_DAY: int = 1  # 1st of month

    # Security
    MIN_N: int = 5
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours

    # Database
    METADATA_DATABASE_URL: str = "sqlite:///./metadata.db"
    CORS_ORIGINS: List[str] = ["*"]

    # Logging configuration
    LOG_LEVEL: str = "INFO"  # Log level for glow_api module
    LOG_UVICORN_ACCESS: str = (
        "INFO"  # Log level for uvicorn.access (endpoint access logs)
    )
    LOG_UVICORN: str = "INFO"  # Log level for uvicorn.error (server logs)

    model_config = SettingsConfigDict(
        env_prefix="GLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "DATA_PREFIXES", "DATA_DEMOGRAPHIC_PREFIXES", "CORS_ORIGINS", mode="before"
    )
    @classmethod
    def parse_list(cls, v) -> List[str]:
        return parse_list(v)

    def warn_insecure_defaults(self) -> None:
        """Emit a warning if the default insecure SECRET_KEY is still in use."""
        import warnings

        if self.SECRET_KEY == "change-me-in-production":
            warnings.warn(
                "SECRET_KEY is set to the default insecure value. "
                "Set GLOW_SECRET_KEY to a strong random secret before deploying.",
                UserWarning,
                stacklevel=2,
            )


settings = Settings()
