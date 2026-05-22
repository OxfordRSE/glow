import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from glow_api.auth import get_current_user
from glow_api.blanket_suppression import execute_query_with_neighbors
from glow_api.dashboard_query_options import build_query_options, validate_query_request
from glow_api.data import DataStore, get_datastore
from glow_api.database import get_db, get_school_by_id
from glow_api.models import (
    QueryRequest,
    QueryResponse,
    QueryResult,
    QueryResultForWave,
    UserRead,
)
from glow_api.settings import settings

router = APIRouter(prefix="/query", tags=["query"])


def sort_key(value: str) -> str:
    """
    Replace trailing _<digits> with zero-padded 10-digit version
    so alphabetical sorting behaves numerically.
    """
    return re.sub(
        r"_(\d+)$",
        lambda m: f"_{int(m.group(1)):010d}",
        value,
    )


@router.post("", response_model=QueryResponse, include_in_schema=False)
@router.post("/", response_model=QueryResponse)
def query(
    request: QueryRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
    datastore: DataStore = Depends(get_datastore),
) -> QueryResponse:
    """Execute a query with blanket suppression.

    This endpoint:
    - Validates that the user has access to the requested school
    - Validates that the variable, waves, and aggregations are allowed
    - Applies blanket suppression to protect small cohorts
    - Returns wave-indexed results for focus school and optionally neighbors
    """
    # Authorization: user must have access to requested school or be admin
    if not current_user.is_admin and request.school_id not in current_user.school_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have access to school {request.school_id}",
        )

    # Get school and neighbors
    focus_school = get_school_by_id(db, request.school_id)
    if focus_school is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"School {request.school_id} not found",
        )

    # Build query options for validation (scoped to focus school)
    dfwl = datastore.to_frozen()
    query_options = build_query_options(dfwl, focus_school.name)

    # Validate request using query options
    valid, error_message = validate_query_request(
        variable=request.variable,
        waves=request.waves,
        aggregations=request.aggregations,
        filters=request.filters,
        query_options=query_options,
        include_neighbors=request.include_neighbors,
    )

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    # Get neighbor schools
    neighbor_schools = []
    if request.include_neighbors:
        if request.neighbor_type == "geographical":
            neighbor_schools = focus_school.geographical_neighbors
        else:
            neighbor_schools = focus_school.statistical_neighbors

    # Get data and check if variable exists
    df = dfwl.df
    if request.variable not in df.columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Variable '{request.variable}' not found in data",
        )

    # Execute query with blanket suppression (wave-indexed)
    query_params = {
        "school": focus_school.name,
        "variable": request.variable,
        "waves": request.waves,
        "group_by": request.aggregations,
        "filters": request.filters,
        "neighbors": [n.name for n in neighbor_schools],
    }

    result = execute_query_with_neighbors(
        df=df,
        query_params=query_params,
        min_n=settings.MIN_N,
    )

    # Format focus school result (wave-indexed)
    focus_wave_results = {}
    for wave, wave_data in result["focus"].items():
        focus_wave_results[wave] = QueryResultForWave(
            suppressed=wave_data["suppressed"],
            suppression_message=wave_data.get("message"),
            results=wave_data.get("data"),
        )

    focus_result = QueryResult(
        school_id=focus_school.id,
        school_name=focus_school.name,
        results=focus_wave_results,
    )

    # Format neighbor results (wave-indexed, only schools with some non-suppressed data)
    neighbor_results = []
    for neighbor_data in result["neighbors"]:
        # Find the school object for this neighbor
        neighbor_school = next(
            (n for n in neighbor_schools if n.name == neighbor_data["school"]), None
        )
        if neighbor_school:
            neighbor_wave_results = {}
            for wave, wave_data in neighbor_data["results"].items():
                neighbor_wave_results[wave] = QueryResultForWave(
                    suppressed=wave_data["suppressed"],
                    suppression_message=wave_data.get("message"),
                    results=wave_data.get("data"),
                )

            neighbor_results.append(
                QueryResult(
                    school_id=neighbor_school.id,
                    school_name=neighbor_school.name,
                    results=neighbor_wave_results,
                )
            )

    return QueryResponse(
        focus_school=focus_result,
        neighbors=neighbor_results,
        variable=request.variable,
        waves=request.waves,
        aggregations=request.aggregations,
        filters=request.filters,
    )
