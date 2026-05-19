from fastapi import APIRouter, Depends

from ib_ox_api.auth import get_current_user
from ib_ox_api.data import DataStore, get_datastore
from ib_ox_api.models import (
    AggregationOption,
    ColumnsResponse,
    DescribeDataResponse,
    FilterOption,
    UserRead,
    VariableOption,
)
from ib_ox_api.query_v2 import build_query_catalog

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/columns", response_model=ColumnsResponse)
def get_columns(
    current_user: UserRead = Depends(get_current_user),
    datastore: DataStore = Depends(get_datastore),
) -> list[str]:
    df = datastore.get_dataframe()
    return list(df.columns)


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
    df = datastore.get_dataframe()
    catalog = build_query_catalog(df)

    # Build variables list (all numeric measures including derived totals)
    variables = [
        VariableOption(value=measure, label_key=f"api.{measure}")
        for measure in catalog.measures + catalog.scores
    ]

    # Build aggregation options (exclude wave and school)
    aggregation_options = [
        AggregationOption(value=dim, label_key=f"api.{dim}")
        for dim in catalog.dimensions
        if dim not in ("wave", "school")
    ]

    # Build filter options (exclude school, include wave)
    filter_options = [
        FilterOption(
            value=dim,
            label_key=f"api.{dim}",
            values=catalog.value_suggestions.get(dim, [])
        )
        for dim in catalog.dimensions
        if dim != "school"
    ]

    return DescribeDataResponse(
        variables=variables,
        aggregation_options=aggregation_options,
        filter_options=filter_options,
    )
