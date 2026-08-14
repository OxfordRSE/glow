"""Authentication and authorization logic."""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, OAuth2PasswordBearer
import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from glow_api import request_context
from glow_api.database import get_db, get_school_by_id, get_user_by_username
from glow_api.metadata_models import School, User
from glow_api.models import TokenData, UserRead
from glow_api.settings import settings

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(db, username)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def _user_model_to_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        school_ids=[s.id for s in user.schools],
        school_names=[s.name for s in user.schools],
        is_active=user.is_active,
        is_admin=user.is_admin,
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserRead:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except jwt.PyJWTError:
        raise credentials_exception

    user = get_user_by_username(db, token_data.username)
    if user is None or not user.is_active:
        raise credentials_exception

    return _user_model_to_read(user)


def get_optional_school_user(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
    school_id: int,
) -> tuple[UserRead, School]:
    """Shared auth check for school-scoped, optionally-authenticated endpoints
    (/query and /dimensions). Preserves the exact status codes/detail strings
    both endpoints already used, and emits one 'auth_assessed' timeline event
    covering every outcome.
    """
    if credentials is None:
        request_context.record_event(
            "auth_assessed", outcome="no_credentials", success=False, school_id=school_id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for school-scoped queries",
        )

    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str | None = payload.get("sub")
        if username is None:
            request_context.record_event(
                "auth_assessed", outcome="invalid_token", success=False, school_id=school_id
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
    except jwt.PyJWTError:
        request_context.record_event(
            "auth_assessed", outcome="invalid_token", success=False, school_id=school_id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        request_context.record_event(
            "auth_assessed",
            outcome="unknown_or_inactive_user",
            success=False,
            username=username,
            school_id=school_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user_school_ids = [s.id for s in user.schools]
    if not user.is_admin and school_id not in user_school_ids:
        request_context.record_event(
            "auth_assessed",
            outcome="forbidden",
            success=False,
            username=username,
            is_admin=user.is_admin,
            school_id=school_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have access to school {school_id}",
        )

    school = get_school_by_id(db, school_id)
    if school is None:
        request_context.record_event(
            "auth_assessed",
            outcome="school_not_found",
            success=False,
            username=username,
            school_id=school_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"School {school_id} not found",
        )

    request_context.record_event(
        "auth_assessed",
        outcome="success",
        success=True,
        username=username,
        is_admin=user.is_admin,
        school_id=school_id,
    )
    return _user_model_to_read(user), school
