"""Router for the /me endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import Optional

from glow_api.database import get_db, get_user_by_username
from glow_api.models import MeResponse, MeAnonymous, MeAuthenticated, SchoolSummary
from glow_api.settings import settings

router = APIRouter(tags=["identity"])

# Use HTTPBearer with auto_error=False to make auth optional
security = HTTPBearer(auto_error=False)


@router.get("/me", response_model=None)
def get_me(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Get current user information or anonymous response.
    
    This endpoint supports both authenticated and anonymous access:
    - No token: returns anonymous response
    - Invalid/expired token: returns 401
    - Valid token: returns authenticated response with school summaries
    """
    # No credentials provided - return anonymous
    if credentials is None:
        return MeAnonymous()
    
    # Try to decode token
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    # Get user from database
    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    # Return authenticated response
    schools = [
        SchoolSummary(id=school.id, name=school.name)
        for school in user.schools
    ]
    
    return MeAuthenticated(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        schools=schools,
    )
