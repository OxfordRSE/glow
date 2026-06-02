"""Router for the /dimensions endpoint."""

import pandas as pd
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


def split_variable_key(variable_key: str) -> tuple[Optional[str], str]:
    """Split a namespaced variable key into form id and raw field name."""
    if "__" in variable_key:
        form_id, raw_key = variable_key.split("__", 1)
        return form_id, raw_key
    return None, variable_key


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
        dfwl = datastore.to_frozen()
        df = dfwl.df
        df = df[df["school"] == school.name]
    else:
        # Dataset-scoped query - use full dataset
        dfwl = datastore.to_frozen()
        df = dfwl.df
    
    # Build variables list (all numeric measures including derived totals)
    variables = sorted([col for col in dfwl.numerical_whitelist if col in df.columns])
    variable_defs = []
    for var in variables:
        form_id, raw_key = split_variable_key(var)
        variable_defs.append(
            VariableDefinition(
                key=var,
                raw_key=raw_key,
                form_id=form_id,
            )
        )
    
    # Build dimensions list (categorical columns, excluding school)
    # Infer type based on whether column is numeric or not
    dimension_defs = []
    for dim in sorted(dfwl.categorical_whitelist):
        if dim in df.columns and dim not in ["school", "wave"]:
            # Determine dimension type based on pandas dtype
            col_dtype = df[dim].dtype
            if pd.api.types.is_numeric_dtype(col_dtype):
                dim_type = "number"
            else:
                dim_type = "string"
            
            dimension_defs.append(DimensionDefinition(key=dim, type=dim_type))
    
    return DimensionsResponse(
        school_id=school_id,
        variables=variable_defs,
        dimensions=dimension_defs,
    )
