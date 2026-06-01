"""Router for the /dimensions endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import Optional

from glow_api.data import DataStore, get_datastore
from glow_api.database import get_db, get_user_by_username, get_school_by_id
from glow_api.models import DimensionsResponse, VariableDefinition, DimensionDefinition
from glow_api.settings import settings

router = APIRouter(tags=["discovery"])

# Use HTTPBearer with auto_error=False to make auth optional for dataset-scoped queries
security = HTTPBearer(auto_error=False)


@router.get("/dimensions", response_model=DimensionsResponse)
def get_dimensions(
    school_id: Optional[int] = Query(None, description="Optional school ID for school-scoped discovery"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    datastore: DataStore = Depends(get_datastore),
) -> DimensionsResponse:
    """Get available variables and dimensions.
    
    This endpoint supports both dataset-scoped and school-scoped discovery:
    - No school_id: returns public dataset-scoped dimensions (anonymous access OK)
    - With school_id: returns school-scoped dimensions (requires authorization)
    
    Returns:
        DimensionsResponse with variables and dimensions available for querying
    """
    # If school_id is provided, we need to check authorization
    if school_id is not None:
        # Must have valid credentials for school-scoped queries
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
        
        # Get data scoped to this school
        df = datastore.to_frozen().df
        df = df[df["school"] == school.name]
    else:
        # Dataset-scoped query - use full dataset
        df = datastore.to_frozen().df
    
    # Get numerical and categorical whitelists
    dfwl = datastore.to_frozen()
    
    # Build variables list (all numeric measures including derived totals)
    variables = sorted([col for col in dfwl.numerical_whitelist if col in df.columns])
    variable_defs = [VariableDefinition(key=var) for var in variables]
    
    # Build dimensions list (categorical columns, excluding school)
    # Infer type based on whether values can be parsed as numbers
    dimension_defs = []
    for dim in sorted(dfwl.categorical_whitelist):
        if dim in df.columns and dim not in ["school", "wave"]:
            # Try to determine if this is a numeric or string dimension
            # For simplicity, assume all are strings for now
            # TODO: Add proper type inference if needed
            dimension_defs.append(DimensionDefinition(key=dim, type="string"))
    
    return DimensionsResponse(
        school_id=school_id,
        variables=variable_defs,
        dimensions=dimension_defs,
    )
