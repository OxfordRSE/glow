from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, RootModel, model_validator


class SuppressionCode(str, Enum):
    SMALL_N = "<5"


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


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
    query_options: Optional["QueryOptions"] = None  # Added for dashboard metadata
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


# ---------------------------------------------------------------------------
# Query Options Models (canonical metadata for dashboard)
# ---------------------------------------------------------------------------
class QueryOptionItem(BaseModel):
    """A single query option (aggregation or filter) with scope information."""

    value: str  # The dimension name (e.g., "yearGroup", "class")
    values: list[str] = Field(default_factory=list)  # Possible values (for filters)
    scope: Literal["shared", "focus_only"] = (
        "shared"  # Whether this applies to neighbors too
    )


class QueryOptions(BaseModel):
    """Query capabilities for a specific school.

    This is the canonical source of truth for what queries can be performed
    and is used for both metadata delivery and request validation.
    """

    variables: list[str]  # All numeric measures including derived totals
    waves: list[str]  # Available wave values
    aggregations: list[QueryOptionItem]  # Grouping dimensions with scope
    filters: list[QueryOptionItem]  # Filter dimensions with scope and possible values


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
    aggregations: list[str] = Field(
        default_factory=list
    )  # e.g., ["yearGroup", "d_sex"]
    filters: dict[str, list] = Field(
        default_factory=dict
    )  # e.g., {"d_ethnicity": ["White"]} (wave is handled separately)
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
    results: Optional[list[QueryRow]] = (
        None  # List of result rows (group_by cols + mean + student_n)
    )


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
