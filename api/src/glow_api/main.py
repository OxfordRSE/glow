import os
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from glow_api.data import get_datastore
from glow_api.database import run_migrations, get_db
from glow_api.logging_config import configure_logging
from glow_api.models import Token
from glow_api.request_logging import RequestLoggingMiddleware
from glow_api.routers import admin, auth, dimensions, me, query, schools
from glow_api.settings import settings

configure_logging()

logger = structlog.get_logger("glow_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application lifespan...")
    settings.warn_insecure_defaults()

    logger.info("Running migrations...")
    run_migrations()
    logger.info("Migrations complete")

    # Skip datastore initialization in test mode
    if not os.getenv("GLOW_TESTING"):
        logger.info("Initializing datastore...")
        ds = get_datastore()
        logger.info("Datastore created, starting up...")
        ds.startup()
        logger.info("Datastore startup complete")
        yield
        logger.info("Shutting down datastore...")
        ds.shutdown()
    else:
        logger.info("Test mode - skipping datastore initialization")
        yield


app = FastAPI(
    title="GLOW API",
    description="Read-only API for GLOW longitudinal questionnaire data",
    version=settings.APP_VERSION,
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
# Added after CORSMiddleware so it becomes the outermost user middleware,
# landing inside Starlette's ServerErrorMiddleware (always outermost) but
# outside CORS — it sees unhandled exceptions before ServerErrorMiddleware
# converts them to the generic 500 response.
app.add_middleware(RequestLoggingMiddleware)

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(me.router)
app.include_router(dimensions.router)
app.include_router(schools.router)
app.include_router(query.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "version": settings.APP_VERSION}


@app.post("/token", response_model=Token, tags=["auth"])
def token_alias(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """Alias for /auth/login for backward compatibility."""
    return auth.login(form_data=form_data, db=db)


@app.get("/")
def root() -> dict:
    return {"title": app.title, "description": app.description, "version": app.version}
