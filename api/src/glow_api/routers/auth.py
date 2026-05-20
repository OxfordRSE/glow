from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username, "is_admin": user.is_admin})
    return Token(access_token=access_token, token_type="bearer")
