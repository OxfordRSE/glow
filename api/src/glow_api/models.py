from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, RootModel, model_validator


class SuppressionCode(str, Enum):
    SMALL_N = "<5"


class FrequencyResult(BaseModel):
    """Wave-indexed results for frequency queries.
    
    Each wave produces its own result, keyed by wave value.
    """
    results: dict[str, "FrequencyResultForWave"]


class FrequencyResultForWave(BaseModel):
    csv: str
    suppressions: dict[str, dict[int, SuppressionCode]]


class MeansResult(BaseModel):
    """Wave-indexed results for means queries.
    
    Each wave produces its own result, keyed by wave value.
    """
    results: dict[str, "MeansResultForWave"]


class MeansResultForWave(BaseModel):
    csv: str
    count_csv: str
    suppressions: dict[str, dict[int, SuppressionCode]]


class WaveChangeResult(BaseModel):
    """Result of a wave-change (within-person longitudinal change) query.

    csv: means of per-student changes, one column per value_column.
    count_csv: number of matched students per group.
    suppressions: cells suppressed due to small N.
    """

    csv: str
    count_csv: str
    suppressions: dict[str, dict[int, SuppressionCode]]


class QueryPlanResult(BaseModel):
    """Wave-indexed result of a query plan execution.
    
    Each wave produces its own result, keyed by wave value.
    """
    results: dict[str, "QueryPlanResultForWave"]


class QueryPlanResultForWave(BaseModel):
    """Result of a query plan execution for a single wave."""
    
    csv: str
    count_csv: str
    suppressions: dict[str, dict[int, SuppressionCode]]
    provenance: list[str] = Field(default_factory=list)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserScope(BaseModel):
    """Pre-filter applied to all queries for this user. Dict of column -> list of allowed values."""

    filters: dict[str, list[str]] = Field(default_factory=dict)


class UserCreate(BaseModel):
    username: str
    password: str
    school_ids: list[int] = Field(default_factory=list)
    is_admin: bool = False


class UserRead(BaseModel):
    id: int
    username: str
    school_ids: list[int] = Field(default_factory=list)
    school_names: list[str] = Field(default_factory=list)
    is_active: bool
    is_admin: bool = False
    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    password: Optional[str] = None
    school_ids: Optional[list[int]] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class SchoolCreate(BaseModel):
    name: str
    size: Optional[str] = None
    category: Optional[str] = None


class SchoolRead(BaseModel):
    id: int
    name: str
    size: Optional[str] = None
    category: Optional[str] = None
    geographical_neighbor_ids: list[int] = Field(default_factory=list)
    statistical_neighbor_ids: list[int] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class SchoolListResponse(RootModel[list[SchoolRead]]):
    """List of schools response wrapper for OpenAPI examples."""
    pass


class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    size: Optional[str] = None
    category: Optional[str] = None
    geographical_neighbor_ids: Optional[list[int]] = None
    statistical_neighbor_ids: Optional[list[int]] = None


class FilterOp(str, Enum):
    EQ = "eq"
    IN = "in"
    NE = "ne"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"


class Filter(BaseModel):
    column: str
    op: FilterOp
    value: str | int | float | list[str | int | float]


class FrequencyQuery(BaseModel):
    """Query for a frequency table.

    waves: one or more waves to query (required, query is run separately for each wave)
    group_by: columns to group by (must be whitelisted categorical columns).
              May be empty to return a single total count.
    filters: additional filters to apply (wave filter is automatically applied)
    value_column: the column to count (optional; if omitted, count rows with distinct uid)
    """

    waves: list[str]
    group_by: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    value_column: Optional[str] = None

    @model_validator(mode="after")
    def validate_waves(self) -> "FrequencyQuery":
        if not self.waves:
            raise ValueError("At least one wave must be specified.")
        return self


class MeansQuery(BaseModel):
    """Query for a means table.

    waves: one or more waves to query (required, query is run separately for each wave)
    group_by: columns to group by
    value_columns: columns to average
    filters: additional filters (wave filter is automatically applied)
    """

    waves: list[str]
    group_by: list[str]
    value_columns: list[str]
    filters: list[Filter] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_waves(self) -> "MeansQuery":
        if not self.waves:
            raise ValueError("At least one wave must be specified.")
        return self


class WaveChangeQuery(BaseModel):
    """Query for within-person longitudinal change between two waves.

    For each student with data in both from_wave and to_wave, computes:
        change = value_at_to_wave - value_at_from_wave

    Then optionally groups by categorical columns and reports the mean change.
    Suppression is applied based on the count of matched students per group.

    from_wave: wave value to use as the baseline (e.g. "1")
    to_wave: wave value to compare against (e.g. "3")
    value_columns: numeric columns to compare (must be in NUMERIC_WHITELIST)
    group_by: categorical columns for grouping (from the from_wave rows)
    filters: additional filters applied before the comparison
    """

    from_wave: str
    to_wave: str
    value_columns: list[str]
    group_by: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)


class QueryMetricKind(str, Enum):
    COUNT_STUDENTS = "count_students"
    MEAN = "mean"


class QueryMetric(BaseModel):
    kind: QueryMetricKind
    column: Optional[str] = None
    as_column: Optional[str] = None

    @model_validator(mode="after")
    def validate_metric(self) -> "QueryMetric":
        if self.kind == QueryMetricKind.COUNT_STUDENTS and self.column is not None:
            raise ValueError("count_students metrics must not specify a column.")
        if self.kind == QueryMetricKind.MEAN and not self.column:
            raise ValueError("mean metrics must specify a column.")
        return self


class QueryFilterStep(BaseModel):
    type: Literal["filter"]
    column: str
    op: FilterOp
    value: str | int | float | list[str | int | float]


class QueryDeriveScoreStep(BaseModel):
    type: Literal["derive_score"]
    score: Literal["bw_wbeing_total"]


class QueryPairWavesStep(BaseModel):
    type: Literal["pair_waves"]
    from_wave: str
    to_wave: str
    measures: list[str]


class QueryBucketBand(BaseModel):
    label: str
    min_students: int = Field(ge=0)
    max_students: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_band(self) -> "QueryBucketBand":
        if self.max_students is not None and self.max_students < self.min_students:
            raise ValueError("max_students must be greater than or equal to min_students.")
        return self


class QueryBucketSchoolSizeStep(BaseModel):
    type: Literal["bucket_school_size"]
    output_column: str = "school_size_bucket"
    bands: list[QueryBucketBand]


class QueryAggregateStep(BaseModel):
    type: Literal["aggregate"]
    group_by: list[str] = Field(default_factory=list)
    metrics: list[QueryMetric]


QueryStep = Annotated[
    QueryFilterStep
    | QueryDeriveScoreStep
    | QueryPairWavesStep
    | QueryBucketSchoolSizeStep
    | QueryAggregateStep,
    Field(discriminator="type"),
]


class QueryPlan(BaseModel):
    """A query plan with one or more waves.
    
    All queries must specify at least one wave. The plan is executed separately
    for each wave, and results are returned as a wave-indexed dictionary.
    """
    waves: list[str]
    steps: list[QueryStep]

    @model_validator(mode="after")
    def validate_plan(self) -> "QueryPlan":
        if not self.waves:
            raise ValueError("At least one wave must be specified.")
        if not self.steps:
            raise ValueError("Query plans must contain at least one step.")
        if self.steps[-1].type != "aggregate":
            raise ValueError("Query plans must end with an aggregate step.")
        return self


class QueryCatalog(BaseModel):
    dimensions: list[str]
    measures: list[str]
    scores: list[str]
    waves: list[str]
    value_suggestions: dict[str, list[str]]
    step_types: list[str]


# ---------------------------------------------------------------------------
# Describe Data Models
# ---------------------------------------------------------------------------


class VariableOption(BaseModel):
    """A variable option with its i18n key."""
    
    value: str  # The column name (e.g., "bw_wbeing_1", "bw_wbeing_total")
    label_key: str  # i18n key with api. prefix (e.g., "api.bw_wbeing_1")


class AggregationOption(BaseModel):
    """An aggregation/grouping option with its i18n key."""
    
    value: str  # The dimension name (e.g., "yearGroup", "d_sex")
    label_key: str  # i18n key with api. prefix (e.g., "api.yearGroup")


class FilterOption(BaseModel):
    """A filter option with its i18n key and possible values."""
    
    value: str  # The dimension name (e.g., "yearGroup", "wave")
    label_key: str  # i18n key with api. prefix (e.g., "api.yearGroup")
    values: list[str]  # Possible values for this filter


class DescribeDataResponse(BaseModel):
    """Response containing all variables, aggregation options, and filter options."""
    
    variables: list[VariableOption]  # All data variables including totals
    aggregation_options: list[AggregationOption]  # Grouping variables (wave excluded)
    filter_options: list[FilterOption]  # Filter variables (wave included with all waves as default)


class ColumnsResponse(RootModel[list[str]]):
    """List of column names response wrapper for OpenAPI examples."""
    pass


# ---------------------------------------------------------------------------
# Safe Query Models (with blanket suppression)
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """Request for a query with blanket suppression.
    
    All queries must specify at least one wave. Results are returned
    separately for each wave.
    """
    
    school_id: int
    variable: str  # Question column or derived score
    waves: list[str]  # Required: one or more waves to query
    aggregations: list[str] = Field(default_factory=list)  # e.g., ["yearGroup", "d_sex"]
    filters: dict[str, list] = Field(default_factory=dict)  # e.g., {"d_ethnicity": ["White"]} (wave is handled separately)
    include_neighbors: bool = False
    neighbor_type: Literal["geographical", "statistical"] = "geographical"

    @model_validator(mode="after")
    def validate_waves(self) -> "QueryRequest":
        if not self.waves:
            raise ValueError("At least one wave must be specified.")
        return self


class QueryResult(BaseModel):
    """Wave-indexed results for a single school with optional suppression.
    
    Each wave produces its own result, keyed by wave value.
    """
    
    school_id: int
    school_name: str
    results: dict[str, "QueryResultForWave"]


class QueryRow(BaseModel):
    """A single row in a query result.
    
    Contains mean and student count, plus any grouping columns.
    Additional fields are allowed to support dynamic group_by columns.
    """
    
    mean: Optional[float] = None
    student_n: int
    # Dynamic fields for group_by columns (d_sex, yearGroup, d_ethnicity, class_)
    # These are validated at runtime based on the aggregations parameter
    model_config = {"extra": "allow"}


class QueryResultForWave(BaseModel):
    """Single school result for a specific wave."""
    
    suppressed: bool
    suppression_message: Optional[str] = None
    results: Optional[list[QueryRow]] = None  # List of result rows (group_by cols + mean + student_n)


class QueryResponse(BaseModel):
    """Response for a query including focus school and neighbors.
    
    Results are wave-indexed - each school has separate results for each wave.
    """
    
    focus_school: QueryResult
    neighbors: list[QueryResult] = Field(default_factory=list)
    variable: str
    waves: list[str]
    aggregations: list[str]
    filters: dict[str, list]


# ---------------------------------------------------------------------------
# Error Response Models
# ---------------------------------------------------------------------------


class ErrorDetailResponse(BaseModel):
    """Standard error response format for API errors."""
    
    detail: str
