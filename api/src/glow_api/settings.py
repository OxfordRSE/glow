from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Any, List

def parse_list(v: Any) -> List[str]:
    if isinstance(v, str):
        v = v.strip()
        if v.startswith("["):
            return json.loads(v)
        return [s.strip() for s in v.split(",") if s.strip()]
    return v


class Settings(BaseSettings):
    DATA_PATH: str = "data/data.csv"
    DATA_REFRESH_HOURS: int = 24
    DATA_PREFIXES: List[str] = ["bw"]
    DATA_DEMOGRAPHIC_PREFIXES: List[str] = ["d"]
    MIN_N: int = 5
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours
    METADATA_DATABASE_URL: str = "sqlite:///./metadata.db"
    CORS_ORIGINS: List[str] = ["*"]

    model_config = SettingsConfigDict(
        env_prefix="GLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATA_PREFIXES", "DATA_DEMOGRAPHIC_PREFIXES", "CORS_ORIGINS", mode="before")
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
