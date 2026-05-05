from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class SuppressionCode(str, Enum):
    SMALL_N = "<5"


class FrequencyResult(BaseModel):
    csv: str
    suppressions: dict[str, dict[int, SuppressionCode]]


class MeansResult(BaseModel):
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


class QueryResult(BaseModel):
    """Result of a query plan execution."""

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
    scope: UserScope = Field(default_factory=UserScope)
    is_admin: bool = False


class UserRead(BaseModel):
    id: int
    username: str
    scope: UserScope
    is_active: bool
    is_admin: bool = False
    student_count: Optional[int] = None
    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    password: Optional[str] = None
    scope: Optional[UserScope] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


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

    group_by: columns to group by (must be whitelisted categorical columns).
              May be empty to return a single total count.
    filters: additional filters to apply
    value_column: the column to count (optional; if omitted, count rows with distinct uid)
    """

    group_by: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    value_column: Optional[str] = None


class MeansQuery(BaseModel):
    """Query for a means table.

    group_by: columns to group by
    value_columns: columns to average
    filters: additional filters
    """

    group_by: list[str]
    value_columns: list[str]
    filters: list[Filter] = Field(default_factory=list)


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
    steps: list[QueryStep]

    @model_validator(mode="after")
    def validate_plan(self) -> "QueryPlan":
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
