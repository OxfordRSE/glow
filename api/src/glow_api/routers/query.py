import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from glow_api.auth import get_current_user
from glow_api.blanket_suppression import execute_query_with_neighbors
from glow_api.data import DataStore, get_datastore
from glow_api.database import get_db, get_school_by_id
from glow_api.models import QueryRequest, QueryResponse, QueryResult, QueryResultForWave, UserRead
from glow_api.query_v2 import build_query_catalog
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


ALLOWED_VARIABLES = sorted([
    # Questionnaire prefixes (individual items)
    "bw_migration",
    "bw_wbeing",
    "bw_selfest",
    "bw_emoreg",
    "bw_stress",
    "bw_coping",
    "bw_emodies",
    "bw_behav",
    "bw_unhealthy",
    "bw_socmtype",
    "bw_activ",
    "bw_staffrel",
    "bw_localenv",
    "bw_future",
    "bw_plans",
    "bw_gmacs",
    "bw_parentsrel",
    "bw_friends",
    "bw_discrim",
    "bw_discloc",
    "bw_bullying",
    "bw_mhcontact",
    # Derived total scores
    "bw_migration_total",
    "bw_wbeing_total",
    "bw_selfest_total",
    "bw_emoreg_total",
    "bw_stress_total",
    "bw_coping_total",
    "bw_emodies_total",
    "bw_behav_total",
    "bw_unhealthy_total",
    "bw_socmtype_total",
    "bw_activ_total",
    "bw_staffrel_total",
    "bw_localenv_total",
    "bw_future_total",
    "bw_plans_total",
    "bw_gmacs_total",
    "bw_parentsrel_total",
    "bw_friends_total",
    "bw_discrim_total",
    "bw_discloc_total",
    "bw_bullying_total",
    "bw_mhcontact_total",
    # Individual questionnaire items
    "bw_activ_1",
    "bw_activ_10",
    "bw_activ_11",
    "bw_activ_2",
    "bw_activ_3",
    "bw_activ_4",
    "bw_activ_5",
    "bw_activ_6",
    "bw_activ_7",
    "bw_activ_8",
    "bw_activ_9",
    "bw_appear_1",
    "bw_arrival_1",
    "bw_attain_1",
    "bw_behav_1",
    "bw_behav_2",
    "bw_behav_3",
    "bw_behav_4",
    "bw_behav_5",
    "bw_behav_6",
    "bw_beinheard_1",
    "bw_bullying_1",
    "bw_bullying_2",
    "bw_bullying_3",
    "bw_careershlp_1",
    "bw_careersed_1",
    "bw_coping_1",
    "bw_coping_2",
    "bw_discloc_1",
    "bw_discloc_2",
    "bw_discloc_3",
    "bw_discloc_4",
    "bw_discloc_5",
    "bw_discloc_6",
    "bw_discloc_7",
    "bw_discrim_1",
    "bw_discrim_2",
    "bw_discrim_3",
    "bw_discrim_4",
    "bw_discrim_5",
    "bw_emodies_1",
    "bw_emodies_10",
    "bw_emodies_2",
    "bw_emodies_3",
    "bw_emodies_4",
    "bw_emodies_5",
    "bw_emodies_6",
    "bw_emodies_7",
    "bw_emodies_8",
    "bw_emodies_9",
    "bw_emoreg_1",
    "bw_emoreg_2",
    "bw_emoreg_3",
    "bw_foodsec_1",
    "bw_freetime_1",
    "bw_friends_1",
    "bw_friends_2",
    "bw_friends_3",
    "bw_friends_4",
    "bw_fruitveg_1",
    "bw_future_1",
    "bw_future_2",
    "bw_future_3",
    "bw_future_4",
    "bw_future_5",
    "bw_future_6",
    "bw_future_7",
    "bw_gmacs_1",
    "bw_gmacs_2",
    "bw_homeenv_1",
    "bw_iso_1",
    "bw_isodays_1",
    "bw_isodur_1",
    "bw_kooth_1",
    "bw_life_sat_1",
    "bw_localenv_1",
    "bw_localenv_2",
    "bw_localenv_3",
    "bw_localenv_4",
    "bw_lonely_1",
    "bw_material_1",
    "bw_mhcontact_1",
    "bw_mhcontact_2",
    "bw_mhcontact_3",
    "bw_mhcontact_4",
    "bw_mhcontact_5",
    "bw_mhcontact_6",
    "bw_migration_1",
    "bw_migration_2",
    "bw_migration_3",
    "bw_parentsrel_1",
    "bw_parentsrel_2",
    "bw_parentsrel_3",
    "bw_parentsrel_4",
    "bw_physact_1",
    "bw_physdur_1",
    "bw_physh_1",
    "bw_plans_1",
    "bw_plans_2",
    "bw_plans_3",
    "bw_plans_4",
    "bw_plans_5",
    "bw_plans_6",
    "bw_plans_7",
    "bw_plans_8",
    "bw_safety_1",
    "bw_schoolconn_1",
    "bw_schpress_1",
    "bw_selfest_1",
    "bw_selfest_2",
    "bw_selfest_3",
    "bw_selfest_4",
    "bw_selfest_5",
    "bw_sleep_1",
    "bw_socmedia_1",
    "bw_socmtype_1",
    "bw_socmtype_2",
    "bw_staffrel_1",
    "bw_staffrel_2",
    "bw_staffrel_3",
    "bw_staffrel_4",
    "bw_stress_1",
    "bw_stress_2",
    "bw_support_1",
    "bw_unhealthy_1",
    "bw_unhealthy_2",
    "bw_unhealthy_3",
    "bw_unhealthy_4",
    "bw_volunteer_1",
    "bw_wbeing_1",
    "bw_wbeing_2",
    "bw_wbeing_3",
    "bw_wbeing_4",
    "bw_wbeing_5",
    "bw_wbeing_6",
    "bw_wbeing_7"
], key=sort_key)

ALLOWED_AGGREGATIONS = ["yearGroup", "d_ethnicity", "d_sex", "class"]

ALLOWED_FILTERS = ["yearGroup", "d_ethnicity", "d_sex", "wave", "class"]


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

    # Validate variable
    if request.variable not in ALLOWED_VARIABLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Variable '{request.variable}' is not allowed. Allowed variables: {ALLOWED_VARIABLES}",
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
    df = datastore.get_dataframe()

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
    df = datastore.get_dataframe()
    if not current_user.is_admin:
        df = df[df["school"].isin(current_user.school_names)]
    return build_query_catalog(df)
