import json
from collections.abc import Generator
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ib_ox_api.settings import settings


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    scope_json = Column(String, nullable=False, default="{}")
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _alembic_ini_path() -> Path:
    """Find alembic.ini by searching upward from this file's location.

    Walks up to 5 parent directories. Resilient to installed-package path variations.
    """
    here = Path(__file__).parent
    level = 0
    while level < 5:
        ini = here / "alembic.ini"
        if ini.exists():
            return ini
        here = here.parent
        level += 1
    raise FileNotFoundError(
        "alembic.ini not found within 5 parent directories of database.py. "
        "Ensure it is present in the api/ directory."
    )


def run_migrations() -> None:
    """Apply all pending Alembic migrations (used at application startup)."""
    ini_path = _alembic_ini_path()
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(ini_path.parent / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(ini_path.parent / "src"))
    # Override the URL from settings so env vars are respected
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(cfg, "head")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user_by_username(db: Session, username: str) -> Optional[UserModel]:
    return db.query(UserModel).filter(UserModel.username == username).first()


def create_user(
    db: Session,
    username: str,
    hashed_password: str,
    scope_json: str = "{}",
    is_active: bool = True,
    is_admin: bool = False,
) -> UserModel:
    user = UserModel(
        username=username,
        hashed_password=hashed_password,
        scope_json=scope_json,
        is_active=is_active,
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user: UserModel,
    hashed_password: Optional[str] = None,
    scope_json: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_admin: Optional[bool] = None,
) -> UserModel:
    if hashed_password is not None:
        user.hashed_password = hashed_password
    if scope_json is not None:
        user.scope_json = scope_json
    if is_active is not None:
        user.is_active = is_active
    if is_admin is not None:
        user.is_admin = is_admin
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: UserModel) -> None:
    db.delete(user)
    db.commit()


def list_users(db: Session) -> list[UserModel]:
    return db.query(UserModel).all()


def scope_json_to_dict(scope_json: str) -> dict:
    """Parse the scope_json string into a dict."""
    try:
        return json.loads(scope_json)
    except (json.JSONDecodeError, TypeError):
        return {}
