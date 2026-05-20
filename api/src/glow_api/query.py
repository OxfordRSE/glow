import io
import re
from dataclasses import dataclass, field

import pandas as pd
from glow_api.data import DataFrameWithWhitelists

from glow_api.models import (
    FilterOp,
    QueryAggregateStep,
    QueryBucketBand,
    QueryBucketSchoolSizeStep,
    QueryCatalog,
    QueryDeriveScoreStep,
    QueryFilterStep,
    QueryMetric,
    QueryMetricKind,
    QueryPairWavesStep,
    QueryPlan,
    QueryPlanResult,
    QueryPlanResultForWave,
    SuppressionCode,
    UserScope,
)
from glow_api.query_utils import _df_to_csv, _normalize_comparable_value, _series_as_strings, apply_user_scope, \
    _apply_single_filter

SAFE_OUTPUT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def build_query_catalog(dfwl: DataFrameWithWhitelists) -> QueryCatalog:
    df = dfwl.df
    value_suggestions: dict[str, list[str]] = {}
    for column in sorted(dfwl.categorical_whitelist):
        if column not in df.columns:
            continue
        series = _series_as_strings(df.dropna(subset=[column]), column)
        value_suggestions[column] = sorted(series.dropna().astype(str).unique().tolist())[:50]

    waves = value_suggestions.get("wave", [])

    return QueryCatalog(
        dimensions=sorted(col for col in dfwl.categorical_whitelist if col in df.columns),
        measures=sorted(col for col in dfwl.numerical_whitelist if col in df.columns and not col.endswith("_total")),
        scores=sorted(col for col in dfwl.numerical_whitelist if col in df.columns and col.endswith("_total")),
        waves=waves,
        value_suggestions=value_suggestions,
        step_types=[
            "filter",
            "derive_score",
            "pair_waves",
            "bucket_school_size",
            "aggregate",
        ],
    )


@dataclass
class SuppressionAwareFrame:
    df: pd.DataFrame
    row_grain: str
    public_dimensions: set[str]
    public_measures: set[str]
    provenance: list[str] = field(default_factory=list)

    @property
    def public_columns(self) -> set[str]:
        return self.public_dimensions | self.public_measures

    def ensure_public_column(self, column: str) -> None:
        if column not in self.public_columns:
            raise ValueError(
                f"Column '{column}' is not available at this stage. "
                f"Available columns: {sorted(self.public_columns)}"
            )

    def ensure_dimension(self, column: str) -> None:
        if column not in self.public_dimensions:
            raise ValueError(
                f"Column '{column}' is not an allowed grouping dimension at this stage. "
                f"Allowed dimensions: {sorted(self.public_dimensions)}"
            )

    def ensure_measure(self, column: str) -> None:
        if column not in self.public_measures:
            raise ValueError(
                f"Column '{column}' is not an allowed measure at this stage. "
                f"Allowed measures: {sorted(self.public_measures)}"
            )


def _initial_frame(dfwl: DataFrameWithWhitelists, scope: UserScope) -> SuppressionAwareFrame:
    df = dfwl.df
    scoped = apply_user_scope(df, scope)
    dimensions = {col for col in dfwl.categorical_whitelist if col in scoped.columns}
    measures = {col for col in dfwl.numerical_whitelist if col in scoped.columns}
    return SuppressionAwareFrame(
        df=scoped.copy(),
        row_grain="student_wave",
        public_dimensions=dimensions,
        public_measures=measures,
    )


def _append_provenance(frame: SuppressionAwareFrame, message: str) -> None:
    frame.provenance.append(message)


def _validate_output_name(name: str) -> None:
    if not SAFE_OUTPUT_NAME_RE.match(name):
        raise ValueError(
            f"Output column '{name}' must match {SAFE_OUTPUT_NAME_RE.pattern!r}."
        )


def _ensure_no_duplicate_output_names(group_by: list[str], metrics: list[QueryMetric]) -> None:
    seen = set(group_by)
    duplicates = [name for name in group_by if group_by.count(name) > 1]
    if duplicates:
        raise ValueError(f"Duplicate group_by columns are not allowed: {sorted(set(duplicates))}")

    for metric in metrics:
        output_name = _metric_output_name(metric)
        if output_name in seen:
            raise ValueError(f"Output column '{output_name}' conflicts with another output column.")
        seen.add(output_name)


def _metric_output_name(metric: QueryMetric) -> str:
    if metric.as_column:
        _validate_output_name(metric.as_column)
        return metric.as_column
    if metric.kind == QueryMetricKind.COUNT_STUDENTS:
        return "student_n"
    assert metric.column is not None
    return metric.column


def _ensure_student_level(frame: SuppressionAwareFrame, step_name: str) -> None:
    if frame.row_grain == "aggregate":
        raise ValueError(f"'{step_name}' cannot run after aggregation.")


def _apply_filter_step(frame: SuppressionAwareFrame, step: QueryFilterStep) -> SuppressionAwareFrame:
    _ensure_student_level(frame, "filter")
    frame.ensure_public_column(step.column)
    filtered = _apply_single_filter(
        frame.df,
        QueryFilterStep.model_construct(
            type="filter",
            column=step.column,
            op=step.op,
            value=step.value,
        ),
    )
    next_frame = SuppressionAwareFrame(
        df=filtered.copy(),
        row_grain=frame.row_grain,
        public_dimensions=set(frame.public_dimensions),
        public_measures=set(frame.public_measures),
        provenance=list(frame.provenance),
    )
    _append_provenance(next_frame, f"Filtered {step.column} {step.op.value} {step.value!r}.")
    return next_frame


def _derive_bw_wbeing_total(frame: SuppressionAwareFrame) -> SuppressionAwareFrame:
    _ensure_student_level(frame, "derive_score")
    if frame.row_grain != "student_wave":
        raise ValueError(
            "bw_wbeing_total can only be derived on student-wave data before pair_waves."
        )

    bw_wbeing_columns = [
        col for col in sorted(frame.df.columns) if re.fullmatch(r"bw_wbeing_[1-9]", col)
    ]
    if not bw_wbeing_columns:
        raise ValueError(
            "Cannot derive bw_wbeing_total because no BeeWell wellbeing item columns are present."
        )

    derived = frame.df.copy()
    derived["bw_wbeing_total"] = (
        derived[bw_wbeing_columns].apply(pd.to_numeric, errors="coerce").sum(axis=1)
    )
    next_frame = SuppressionAwareFrame(
        df=derived,
        row_grain=frame.row_grain,
        public_dimensions=set(frame.public_dimensions),
        public_measures=set(frame.public_measures) | {"bw_wbeing_total"},
        provenance=list(frame.provenance),
    )
    _append_provenance(
        next_frame,
        "Derived bw_wbeing_total from available BeeWell wellbeing item columns.",
    )
    return next_frame


def _apply_derive_score_step(
    frame: SuppressionAwareFrame, step: QueryDeriveScoreStep
) -> SuppressionAwareFrame:
    if step.score == "bw_wbeing_total":
        return _derive_bw_wbeing_total(frame)
    raise ValueError(f"Unsupported score '{step.score}'.")


def _apply_pair_waves_step(
    frame: SuppressionAwareFrame, step: QueryPairWavesStep
) -> SuppressionAwareFrame:
    _ensure_student_level(frame, "pair_waves")
    if frame.row_grain != "student_wave":
        raise ValueError("pair_waves can only be applied once and only to student-wave data.")
    if "wave" not in frame.df.columns:
        raise ValueError("pair_waves requires a 'wave' column.")

    for measure in step.measures:
        frame.ensure_measure(measure)

    wave_series = _series_as_strings(frame.df, "wave")
    baseline = frame.df[wave_series == _normalize_comparable_value(step.from_wave)].copy()
    comparison = frame.df[wave_series == _normalize_comparable_value(step.to_wave)].copy()

    baseline_dims = [col for col in sorted(frame.public_dimensions - {"wave"}) if col in baseline.columns]
    baseline_cols = ["uid"] + baseline_dims + step.measures
    comparison_cols = ["uid"] + step.measures

    merged = baseline[baseline_cols].merge(
        comparison[comparison_cols],
        on="uid",
        suffixes=("_baseline", "_comparison"),
    )

    for measure in step.measures:
        merged[f"baseline_{measure}"] = pd.to_numeric(
            merged[f"{measure}_baseline"], errors="coerce"
        )
        merged[f"comparison_{measure}"] = pd.to_numeric(
            merged[f"{measure}_comparison"], errors="coerce"
        )
        merged[f"change_{measure}"] = (
            merged[f"comparison_{measure}"] - merged[f"baseline_{measure}"]
        )

    pair_measure_cols = {
        f"baseline_{measure}" for measure in step.measures
    } | {
        f"comparison_{measure}" for measure in step.measures
    } | {
        f"change_{measure}" for measure in step.measures
    }

    keep_cols = ["uid"] + baseline_dims + sorted(pair_measure_cols)
    next_frame = SuppressionAwareFrame(
        df=merged[keep_cols].copy(),
        row_grain="student_pair",
        public_dimensions=set(baseline_dims),
        public_measures=pair_measure_cols,
        provenance=list(frame.provenance),
    )
    _append_provenance(
        next_frame,
        f"Paired waves {step.from_wave} -> {step.to_wave} for {', '.join(step.measures)}.",
    )
    return next_frame


def _bucket_label_for_count(count: int, bands: list[QueryBucketBand]) -> str | None:
    for band in bands:
        if count < band.min_students:
            continue
        if band.max_students is not None and count > band.max_students:
            continue
        return band.label
    return None


def _apply_bucket_school_size_step(
    frame: SuppressionAwareFrame, step: QueryBucketSchoolSizeStep
) -> SuppressionAwareFrame:
    _ensure_student_level(frame, "bucket_school_size")
    frame.ensure_dimension("school")
    _validate_output_name(step.output_column)

    school_counts = frame.df.groupby("school")["uid"].nunique()
    bucket_map: dict[str, str] = {}
    for school, student_count in school_counts.items():
        label = _bucket_label_for_count(int(student_count), step.bands)
        if label is None:
            raise ValueError(
                f"No bucket matched school '{school}' with {student_count} students."
            )
        bucket_map[str(school)] = label

    derived = frame.df.copy()
    derived[step.output_column] = derived["school"].astype(str).map(bucket_map)
    next_frame = SuppressionAwareFrame(
        df=derived,
        row_grain=frame.row_grain,
        public_dimensions=set(frame.public_dimensions) | {step.output_column},
        public_measures=set(frame.public_measures),
        provenance=list(frame.provenance),
    )
    _append_provenance(
        next_frame,
        f"Bucketed schools into {step.output_column} using distinct-student counts.",
    )
    return next_frame


def _series_from_grouped(
    df: pd.DataFrame,
    group_by: list[str],
    column: str,
    kind: QueryMetricKind,
) -> tuple[pd.Series, pd.Series]:
    if kind == QueryMetricKind.COUNT_STUDENTS:
        if group_by:
            counts = df.groupby(group_by)["uid"].nunique()
            return counts.astype(float), counts.astype(float)
        count = float(df["uid"].nunique())
        series = pd.Series([count], name=column)
        return series, series.copy()

    sub = df.dropna(subset=[column])
    if group_by:
        grouped = sub.groupby(group_by)
        values = grouped[column].mean()
        counts = grouped["uid"].nunique().astype(float)
        return values, counts

    values = pd.Series([sub[column].mean()], name=column)
    counts = pd.Series([float(sub["uid"].nunique())], name=column)
    return values, counts


def _reset_result_index(df: pd.DataFrame, group_by: list[str]) -> pd.DataFrame:
    if group_by:
        return df.reset_index()
    return df.reset_index(drop=True)


def _apply_aggregate_step(
    frame: SuppressionAwareFrame,
    step: QueryAggregateStep,
    min_n: int,
) -> QueryPlanResultForWave:
    _ensure_student_level(frame, "aggregate")
    for column in step.group_by:
        frame.ensure_dimension(column)
    if not step.metrics:
        raise ValueError("aggregate steps must contain at least one metric.")

    _ensure_no_duplicate_output_names(step.group_by, step.metrics)

    values_parts: dict[str, pd.Series] = {}
    counts_parts: dict[str, pd.Series] = {}

    for metric in step.metrics:
        output_name = _metric_output_name(metric)
        if metric.kind == QueryMetricKind.MEAN:
            assert metric.column is not None
            frame.ensure_measure(metric.column)
            values, counts = _series_from_grouped(
                frame.df, step.group_by, metric.column, QueryMetricKind.MEAN
            )
        else:
            values, counts = _series_from_grouped(
                frame.df, step.group_by, output_name, QueryMetricKind.COUNT_STUDENTS
            )
        values_parts[output_name] = values
        counts_parts[output_name] = counts

    result_df = _reset_result_index(pd.DataFrame(values_parts), step.group_by)
    counts_df = _reset_result_index(pd.DataFrame(counts_parts), step.group_by)

    suppressions: dict[str, dict[int, SuppressionCode]] = {}
    metric_columns = [_metric_output_name(metric) for metric in step.metrics]
    for column in metric_columns:
        col_suppressions: dict[int, SuppressionCode] = {}
        for idx in counts_df.index:
            n = counts_df.at[idx, column]
            if pd.isna(n) or float(n) < min_n:
                result_df.at[idx, column] = float("nan")
                counts_df.at[idx, column] = float("nan")
                col_suppressions[int(idx)] = SuppressionCode.SMALL_N
        if col_suppressions:
            suppressions[column] = col_suppressions

    provenance = list(frame.provenance)
    provenance.append(
        "Aggregated metrics with suppression based on contributing distinct-student N."
    )
    return QueryPlanResultForWave(
        csv=_df_to_csv(result_df),
        count_csv=_df_to_csv(counts_df),
        suppressions=suppressions,  # type: ignore[arg-type]
        provenance=provenance,
    )


def execute_query(
    df: pd.DataFrame,
    plan: QueryPlan,
    scope: UserScope,
    min_n: int,
) -> QueryPlanResult:
    """Execute a query plan for each specified wave.
    
    Returns a wave-indexed dictionary of results.
    """
    from glow_api.models import Filter
    
    results = {}
    
    for wave in plan.waves:
        # Start with initial frame for this wave
        frame = _initial_frame(df, scope)
        
        # Apply wave filter first
        wave_filter = QueryFilterStep(
            type="filter",
            column="wave",
            op=FilterOp.EQ,
            value=wave
        )
        frame = _apply_filter_step(frame, wave_filter)
        
        # Execute the rest of the plan
        for step in plan.steps:
            if step.type == "filter":
                frame = _apply_filter_step(frame, step)
            elif step.type == "derive_score":
                frame = _apply_derive_score_step(frame, step)
            elif step.type == "pair_waves":
                frame = _apply_pair_waves_step(frame, step)
            elif step.type == "bucket_school_size":
                frame = _apply_bucket_school_size_step(frame, step)
            elif step.type == "aggregate":
                results[wave] = _apply_aggregate_step(frame, step, min_n)
                break  # Aggregate is always the last step
            else:
                raise ValueError(f"Unsupported step type '{step.type}'.")
        
        if wave not in results:
            raise ValueError("Query plans must end with an aggregate step.")
    
    return QueryPlanResult(results=results)


build_query_v2_catalog = build_query_catalog
execute_query_v2 = execute_query
