"""
Database configuration and session management for metadata database.
"""

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ib_ox_api.metadata_models import Base, School, User
from ib_ox_api.settings import settings

# Create engine for metadata database
engine = create_engine(
    settings.METADATA_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _alembic_ini_path() -> Path:
    """Find alembic.ini by searching upward from this file's location."""
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
    cfg.set_main_option("sqlalchemy.url", settings.METADATA_DATABASE_URL)
    command.upgrade(cfg, "head")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# User CRUD operations
def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def create_user(
    db: Session,
    username: str,
    hashed_password: str,
    is_active: bool = True,
    is_admin: bool = False,
    school_ids: list[int] | None = None,
) -> User:
    user = User(
        username=username,
        hashed_password=hashed_password,
        is_active=is_active,
        is_admin=is_admin,
    )
    if school_ids:
        schools = db.query(School).filter(School.id.in_(school_ids)).all()
        user.schools = schools
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user: User,
    hashed_password: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
    school_ids: list[int] | None = None,
) -> User:
    if hashed_password is not None:
        user.hashed_password = hashed_password
    if is_active is not None:
        user.is_active = is_active
    if is_admin is not None:
        user.is_admin = is_admin
    if school_ids is not None:
        schools = db.query(School).filter(School.id.in_(school_ids)).all()
        user.schools = schools
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()


def list_users(db: Session) -> list[User]:
    return db.query(User).all()


# School CRUD operations
def get_school_by_name(db: Session, name: str) -> School | None:
    return db.query(School).filter(School.name == name).first()


def get_school_by_id(db: Session, school_id: int) -> School | None:
    return db.query(School).filter(School.id == school_id).first()


def create_school(
    db: Session,
    name: str,
    size: str | None = None,
    category: str | None = None,
) -> School:
    school = School(name=name, size=size, category=category)
    db.add(school)
    db.commit()
    db.refresh(school)
    return school


def update_school(
    db: Session,
    school: School,
    name: str | None = None,
    size: str | None = None,
    category: str | None = None,
) -> School:
    if name is not None:
        school.name = name
    if size is not None:
        school.size = size
    if category is not None:
        school.category = category
    db.commit()
    db.refresh(school)
    return school


def delete_school(db: Session, school: School) -> None:
    db.delete(school)
    db.commit()


def list_schools(db: Session) -> list[School]:
    return db.query(School).all()


def set_geographical_neighbors(
    db: Session, school: School, neighbor_ids: list[int]
) -> School:
    """Set geographical neighbors for a school (reciprocal relationship)."""
    neighbors = db.query(School).filter(School.id.in_(neighbor_ids)).all()
    school.geographical_neighbors = neighbors
    
    # Make reciprocal
    for neighbor in neighbors:
        if school not in neighbor.geographical_neighbors:
            neighbor.geographical_neighbors.append(school)
    
    db.commit()
    db.refresh(school)
    return school


def set_statistical_neighbors(
    db: Session, school: School, neighbor_ids: list[int]
) -> School:
    """Set statistical neighbors for a school (reciprocal relationship)."""
    neighbors = db.query(School).filter(School.id.in_(neighbor_ids)).all()
    school.statistical_neighbors = neighbors
    
    # Make reciprocal
    for neighbor in neighbors:
        if school not in neighbor.statistical_neighbors:
            neighbor.statistical_neighbors.append(school)
    
    db.commit()
    db.refresh(school)
    return school
