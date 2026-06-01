"""Period-oriented multi-variable query endpoint."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from glow_api import __version__
from glow_api.canonical_query import normalize_query
from glow_api.query_execution import execute_query, compute_query_etag
from glow_api.normalization import normalize_submissions
from glow_api.data import DataStore, get_datastore
from glow_api.database import get_db, get_school_by_id
from glow_api.settings import settings

router = APIRouter(prefix="/query", tags=["query"])

# Use HTTPBearer with auto_error=False to make auth optional for dataset-scoped queries
security = HTTPBearer(auto_error=False)

@router.get("", response_model=None, include_in_schema=False)
@router.get("/", response_model=None)
def query_get(
    response: Response,
    v: list[str] = Query(default=[], description="Variable names (repeatable)"),
    d: list[str] = Query(default=[], description="Dimension names (repeatable)"),
    variable_prefix: list[str] = Query(default=[], description="Variable prefixes (repeatable)"),
    school_id: Optional[int] = Query(None, description="Optional school ID for school-scoped query"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    datastore: DataStore = Depends(get_datastore),
) -> dict:
    """Execute a new period-oriented multi-variable query.
    
    This endpoint supports:
    - Dataset-scoped queries (no school_id, anonymous access OK)
    - School-scoped queries (with school_id, requires authorization)
    - Variable selection via repeated 'v' params or 'variable_prefix' params
    - Dimension selection via repeated 'd' params
    - Period-organized results with independent suppression per period
    - ETag-based caching with If-None-Match support
    
    Returns:
        NewQueryResponse with period-organized multi-variable results
    """
    # Normalize query parameters
    canonical = normalize_query(
        school_id=school_id,
        v=v,
        d=d,
        variable_prefix=variable_prefix,
    )
    
    # Get dataset version for ETag
    dfwl = datastore.to_frozen()
    dataset_version = dfwl.metadata.get("_etag", "unknown")
    
    # Compute ETag
    etag = compute_query_etag(
        query=canonical,
        dataset_version=dataset_version,
        api_version=__version__,
    )
    
    # Check If-None-Match
    if if_none_match and if_none_match == etag:
        # Data hasn't changed
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return {}
    
    # Set ETag header
    response.headers["ETag"] = etag
    
    # If school_id is provided, check authorization
    if school_id is not None:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required for school-scoped queries",
            )
        
        # Decode and validate token
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
        from glow_api.database import get_user_by_username
        user = get_user_by_username(db, username)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
        
        # Check if user has access to the requested school
        user_school_ids = [s.id for s in user.schools]
        if not user.is_admin and school_id not in user_school_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have access to school {school_id}",
            )
        
        # Verify school exists
        school = get_school_by_id(db, school_id)
        if school is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"School {school_id} not found",
            )
        
        # Filter data to this school
        df = dfwl.df
        df = df[df["school"] == school.name]
    else:
        # Dataset-scoped query
        df = dfwl.df
    
    # Normalize submissions (add period_id if not already present)
    if "period_id" not in df.columns:
        df = normalize_submissions(df)
    
    # Get numerical whitelist
    numerical_whitelist = dfwl.numerical_whitelist
    
    # Execute query
    result = execute_query(
        df=df,
        query=canonical,
        numerical_whitelist=numerical_whitelist,
        min_n=settings.MIN_N,
    )
    
    return result
