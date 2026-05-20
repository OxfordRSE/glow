from fastapi import APIRouter, Depends

from glow_api.auth import get_current_user
from glow_api.data import DataStore, get_datastore
from glow_api.models import (
    ColumnsResponse,
    DescribeDataResponse,
    FilterOption,
    UserRead,
)
from glow_api.query import build_query_catalog

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/columns", response_model=ColumnsResponse)
def get_columns(
    current_user: UserRead = Depends(get_current_user),
    datastore: DataStore = Depends(get_datastore),
) -> list[str]:
    dfwl = datastore.to_frozen()
    return list(set([*dfwl.categorical_whitelist, *dfwl.numerical_whitelist]))


@router.get("/describe", response_model=DescribeDataResponse)
def describe_data(
    current_user: UserRead = Depends(get_current_user),
    datastore: DataStore = Depends(get_datastore),
) -> DescribeDataResponse:
    """
    Get all available variables, aggregation options, and filter options.
    All labels are returned as i18n keys with 'api.' prefix.
    School is always used for grouping (focus school + neighbors) so it's excluded from both aggregations and filters.
    Wave is included in filters (with all values selected by default) but excluded from aggregations.
    """
    dfwl = datastore.to_frozen()
    catalog = build_query_catalog(dfwl)

    # Build variables list (all numeric measures including derived totals)
    variables = [measure for measure in catalog.measures + catalog.scores]

    # Build aggregation options (exclude wave and school)
    aggregation_options = catalog.dimensions

    # Build filter options (exclude school, include wave)
    filter_options = [
        FilterOption(
            value=dim,
            values=catalog.value_suggestions.get(dim, [])
        )
        for dim in catalog.dimensions
    ]

    return DescribeDataResponse(
        variables=variables,
        aggregation_options=aggregation_options,
        filter_options=filter_options,
    )
