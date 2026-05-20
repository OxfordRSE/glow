from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATA_PATH: str = "data/data.csv"
    DATA_REFRESH_HOURS: int = 24
    MIN_N: int = 5
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours
    METADATA_DATABASE_URL: str = "sqlite:///./metadata.db"
    CORS_ORIGINS: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_prefix="GLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

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
