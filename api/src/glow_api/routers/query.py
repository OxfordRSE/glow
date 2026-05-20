import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from glow_api.auth import get_current_user
from glow_api.blanket_suppression import execute_query_with_neighbors
from glow_api.data import DataStore, get_datastore
from glow_api.database import get_db, get_school_by_id
from glow_api.models import QueryRequest, QueryResponse, QueryResult, QueryResultForWave, UserRead
from glow_api.query import build_query_catalog
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

ALLOWED_AGGREGATIONS = ["yearGroup", "d_ethnicity", "d_sex", "class"]

ALLOWED_FILTERS = ["yearGroup", "d_ethnicity", "d_sex", "class"]


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

    dfwl = datastore.to_frozen()
    allowed_variables = [*dfwl.categorical_whitelist, *dfwl.numerical_whitelist]
    # Validate variable
    if request.variable not in allowed_variables:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Variable '{request.variable}' is not allowed. Allowed variables: {allowed_variables}",
        )

    # Validate aggregations
    for agg in request.aggregations:
        if agg not in ALLOWED_AGGREGATIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Aggregation '{agg}' is not allowed. Allowed aggregations: {ALLOWED_AGGREGATIONS}",
            )

    # Validate filters
    for filter_col in request.filters.keys():
        if filter_col not in ALLOWED_FILTERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Filter '{filter_col}' is not allowed. Allowed filters: {ALLOWED_FILTERS}",
            )

    # Class aggregation not allowed with neighbors
    if "class" in request.aggregations and request.include_neighbors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class aggregation is only allowed for focus school (not with neighbors)",
        )

    # Get school and neighbors
    focus_school = get_school_by_id(db, request.school_id)
    if focus_school is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"School {request.school_id} not found",
        )

    neighbor_schools = []
    if request.include_neighbors:
        if request.neighbor_type == "geographical":
            neighbor_schools = focus_school.geographical_neighbors
        else:
            neighbor_schools = focus_school.statistical_neighbors

    # Get data
    df = dfwl.df

    # Check if variable exists in dataframe
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
        neighbor_school = next((n for n in neighbor_schools if n.name == neighbor_data["school"]), None)
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


@router.get("/catalog")
def query_catalog(
    current_user: UserRead = Depends(get_current_user),
    datastore: DataStore = Depends(get_datastore),
):
    """Get query catalog for building queries."""
    dfwl = datastore.to_frozen()
    if not current_user.is_admin:
        dfwl.df = dfwl.df[dfwl.df["school"].isin(current_user.school_names)]
    return build_query_catalog(dfwl)
