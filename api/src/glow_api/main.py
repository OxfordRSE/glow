import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from glow_api import __version__
from glow_api.auth import authenticate_user, create_access_token
from glow_api.data import datastore
from glow_api.database import run_migrations, get_db
from glow_api.models import Token
from glow_api.routers import admin, auth, data, query, schools
from glow_api.settings import settings


def configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                }
            },
            "loggers": {
                "glow_api": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                }
            },
        }
    )


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.warn_insecure_defaults()
    run_migrations()
    datastore.startup()
    yield
    datastore.shutdown()


app = FastAPI(
    title="GLOW API",
    description="Read-only API for GLOW longitudinal questionnaire data",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
    root_path="/api",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(schools.router)
app.include_router(data.router)
app.include_router(query.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/token", response_model=Token, tags=["auth"])
def token_alias(
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: Session = Depends(get_db),
) -> Token:
    """Alias for /auth/login for backward compatibility."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username, "is_admin": user.is_admin})
    return Token(access_token=access_token, token_type="bearer")


@app.get("/")
def root() -> dict:
    return {
        "title": app.title,
        "description": app.description,
        "version": app.version
    }
