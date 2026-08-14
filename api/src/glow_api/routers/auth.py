from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from glow_api import request_context
from glow_api.auth import authenticate_user, create_access_token
from glow_api.database import get_db
from glow_api.models import Token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login/", response_model=Token)
@router.post("/login", response_model=Token, include_in_schema=False)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        request_context.record_event(
            "auth_assessed",
            outcome="login_failed",
            success=False,
            username=form_data.username,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request_context.record_event(
        "auth_assessed",
        outcome="login_success",
        success=True,
        username=user.username,
        is_admin=user.is_admin,
        user_id=user.id,
    )
    access_token = create_access_token(
        data={"sub": user.username, "is_admin": user.is_admin}
    )
    return Token(access_token=access_token, token_type="bearer")
