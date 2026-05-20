import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from glow_api.models import QueryPlan, QueryPlanResult, UserScope
from glow_api.query import execute_query

MIN_N_FOR_DOCS = 5
MAX_DOC_ROWS = 8


def _resolve_docs_path() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "docs" / "query-builder.md"
        if candidate.exists():
            return candidate
        if (parent / "README.md").exists() and (parent / "docs").exists():
            return candidate
    return Path.cwd() / "docs" / "query-builder.md"


DOCS_PATH = _resolve_docs_path()


@dataclass(frozen=True)
class QueryExample:
    slug: str
    title: str
    question: str
    plan: QueryPlan
    expected_rows: list[dict[str, Any]]
    expected_count_rows: list[dict[str, Any]]
    expected_suppressions: dict[str, dict[str, str]]
    sort_by: tuple[str, ...] = ()


def query_examples() -> tuple[QueryExample, ...]:
    return (
        QueryExample(
            slug="count-by-school",
            title="Count students by school",
            question="How many distinct students are in scope for each school?",
            plan=QueryPlan.model_validate(
                {
                    "waves": ["1", "2", "3"],
                    "steps": [
                        {
                            "type": "aggregate",
                            "group_by": ["school"],
                            "metrics": [{"kind": "count_students"}],
                        }
                    ]
                }
            ),
            expected_rows=[
                {"school": "Focus School Academy", "student_n": 5.0},
                {"school": "Neighbouring School", "student_n": 5.0},
            ],
            expected_count_rows=[
                {"school": "Focus School Academy", "student_n": 5.0},
                {"school": "Neighbouring School", "student_n": 5.0},
            ],
            expected_suppressions={},
            sort_by=("school",),
        ),
        QueryExample(
            slug="mean-derived-score-by-school",
            title="Mean derived BeeWell score by school",
            question="What is the mean derived `bw_wbeing_total` for each school?",
            plan=QueryPlan.model_validate(
                {
                    "waves": ["1", "2", "3"],
                    "steps": [
                        {"type": "derive_score", "score": "bw_wbeing_total"},
                        {
                            "type": "aggregate",
                            "group_by": ["school"],
                            "metrics": [{"kind": "mean", "column": "bw_wbeing_total"}],
                        },
                    ]
                }
            ),
            expected_rows=[
                {"school": "Focus School Academy", "bw_wbeing_total": 9.8},
                {"school": "Neighbouring School", "bw_wbeing_total": 8.8},
            ],
            expected_count_rows=[
                {"school": "Focus School Academy", "bw_wbeing_total": 5.0},
                {"school": "Neighbouring School", "bw_wbeing_total": 5.0},
            ],
            expected_suppressions={},
            sort_by=("school",),
        ),
        QueryExample(
            slug="longitudinal-change-by-school",
            title="Mean within-student change after a baseline threshold",
            question=(
                "Among students whose baseline `bw_wbeing_total` is at least 3, what is the mean "
                "change from wave 1 to wave 2 by school?"
            ),
            plan=QueryPlan.model_validate(
                {
                    "waves": ["1", "2", "3"],
                    "steps": [
                        {"type": "derive_score", "score": "bw_wbeing_total"},
                        {
                            "type": "pair_waves",
                            "from_wave": "1",
                            "to_wave": "2",
                            "measures": ["bw_wbeing_total"],
                        },
                        {
                            "type": "filter",
                            "column": "baseline_bw_wbeing_total",
                            "op": "gte",
                            "value": 3,
                        },
                        {
                            "type": "aggregate",
                            "group_by": ["school"],
                            "metrics": [
                                {
                                    "kind": "mean",
                                    "column": "change_bw_wbeing_total",
                                    "as_column": "avg_change",
                                },
                                {"kind": "count_students"},
                            ],
                        },
                    ]
                }
            ),
            expected_rows=[{"school": "Focus School Academy", "avg_change": 0.8, "student_n": 5.0}],
            expected_count_rows=[{"school": "Focus School Academy", "avg_change": 5.0, "student_n": 5.0}],
            expected_suppressions={},
            sort_by=("school",),
        ),
        QueryExample(
            slug="bucketed-school-size-by-year-group",
            title="Mean score after school-size bucketing",
            question=(
                "What is the mean `bw_wbeing_total` by year group after bucketing schools by "
                "distinct-student participation?"
            ),
            plan=QueryPlan.model_validate(
                {
                    "waves": ["1", "2", "3"],
                    "steps": [
                        {"type": "derive_score", "score": "bw_wbeing_total"},
                        {
                            "type": "bucket_school_size",
                            "output_column": "school_size_bucket",
                            "bands": [
                                {"label": "small", "min_students": 0, "max_students": 4},
                                {"label": "medium", "min_students": 5, "max_students": 9},
                                {"label": "large", "min_students": 10},
                            ],
                        },
                        {
                            "type": "aggregate",
                            "group_by": ["school_size_bucket", "yearGroup"],
                            "metrics": [{"kind": "mean", "column": "bw_wbeing_total"}],
                        },
                    ]
                }
            ),
            expected_rows=[
                {"school_size_bucket": "medium", "yearGroup": 7, "bw_wbeing_total": 9.8},
                {"school_size_bucket": "medium", "yearGroup": 8, "bw_wbeing_total": 8.8},
            ],
            expected_count_rows=[
                {"school_size_bucket": "medium", "yearGroup": 7, "bw_wbeing_total": 5.0},
                {"school_size_bucket": "medium", "yearGroup": 8, "bw_wbeing_total": 5.0},
            ],
            expected_suppressions={},
            sort_by=("school_size_bucket", "yearGroup"),
        ),
        QueryExample(
            slug="suppressed-small-longitudinal-cohort",
            title="Suppressed small longitudinal cohort",
            question=(
                "How many students had a baseline `bw_wbeing_total` above 10 when matched from wave 1 "
                "to wave 2, by school?"
            ),
            plan=QueryPlan.model_validate(
                {
                    "waves": ["1", "2", "3"],
                    "steps": [
                        {"type": "derive_score", "score": "bw_wbeing_total"},
                        {
                            "type": "pair_waves",
                            "from_wave": "1",
                            "to_wave": "2",
                            "measures": ["bw_wbeing_total"],
                        },
                        {
                            "type": "filter",
                            "column": "baseline_bw_wbeing_total",
                            "op": "gt",
                            "value": 10,
                        },
                        {
                            "type": "aggregate",
                            "group_by": ["school"],
                            "metrics": [{"kind": "count_students"}],
                        },
                    ]
                }
            ),
            expected_rows=[{"school": "Focus School Academy", "student_n": float("nan")}],
            expected_count_rows=[{"school": "Focus School Academy", "student_n": float("nan")}],
            expected_suppressions={"student_n": {"0": "<5"}},
            sort_by=("school",),
        ),
    )


def execute_example(
    example: QueryExample,
    df: pd.DataFrame,
    *,
    scope: UserScope | None = None,
    min_n: int = MIN_N_FOR_DOCS,
) -> QueryPlanResult:
    return execute_query(df, example.plan, scope or UserScope(), min_n)


def parse_result_csv(csv_text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(csv_text))


def _sort_records(df: pd.DataFrame, sort_by: tuple[str, ...]) -> pd.DataFrame:
    if not sort_by or df.empty:
        return df.reset_index(drop=True)
    return df.sort_values(list(sort_by), kind="stable").reset_index(drop=True)


def assert_example_result(example: QueryExample, result: QueryPlanResult) -> None:
    actual_values = _sort_records(parse_result_csv(result.csv), example.sort_by)
    actual_counts = _sort_records(parse_result_csv(result.count_csv), example.sort_by)
    expected_values = _sort_records(pd.DataFrame(example.expected_rows), example.sort_by)
    expected_counts = _sort_records(pd.DataFrame(example.expected_count_rows), example.sort_by)

    assert list(actual_values.columns) == list(expected_values.columns)
    assert list(actual_counts.columns) == list(expected_counts.columns)
    assert len(actual_values.index) == len(expected_values.index)
    assert len(actual_counts.index) == len(expected_counts.index)

    for actual_df, expected_df in ((actual_values, expected_values), (actual_counts, expected_counts)):
        for row_idx in range(len(expected_df.index)):
            for column in expected_df.columns:
                expected = expected_df.at[row_idx, column]
                actual = actual_df.at[row_idx, column]
                if pd.isna(expected):
                    assert pd.isna(actual), f"{example.slug}: expected NaN in {column}, got {actual!r}"
                    continue
                assert actual == expected, (
                    f"{example.slug}: expected {column}={expected!r}, got {actual!r}"
                )

    actual_suppressions = {
        column: {
            str(index): code.value if hasattr(code, "value") else str(code)
            for index, code in codes.items()
        }
        for column, codes in result.suppressions.items()
    }
    assert actual_suppressions == example.expected_suppressions


def _render_markdown_table(df: pd.DataFrame, *, max_rows: int = MAX_DOC_ROWS) -> str:
    if df.empty:
        return "_No rows returned._"

    display_df = df.head(max_rows).copy()
    display_df = display_df.where(pd.notna(display_df), "")
    headers = [str(column) for column in display_df.columns]
    rows = [[str(value) for value in row] for row in display_df.itertuples(index=False, name=None)]
    widths = [
        max(len(headers[idx]), *(len(row[idx]) for row in rows))
        for idx in range(len(headers))
    ]

    def render_row(values: list[str]) -> str:
        return "| " + " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(values)) + " |"

    lines = [
        render_row(headers),
        "| " + " | ".join("-" * widths[idx] for idx in range(len(headers))) + " |",
    ]
    lines.extend(render_row(row) for row in rows)

    if len(df.index) > max_rows:
        lines.append("")
        lines.append(f"_Showing first {max_rows} of {len(df.index)} rows._")

    return "\n".join(lines)


def describe_suppression_checkpoints(plan: QueryPlan, *, min_n: int = MIN_N_FOR_DOCS) -> list[str]:
    checkpoints = [
        "Before step execution, user scope filters are applied and `uid` is retained internally so "
        "distinct-student counts can be computed later without making identifiers public."
    ]

    for index, step in enumerate(plan.steps, start=1):
        prefix = f"Step {index} `{step.type}`:"
        if step.type == "filter":
            checkpoints.append(
                f"{prefix} validates that `{step.column}` is public at this stage; it narrows the "
                "cohort but does not publish a value or apply `min_n` yet."
            )
        elif step.type == "derive_score":
            checkpoints.append(
                f"{prefix} derives an approved measure on row-level data; suppression still waits "
                "for the terminal aggregate."
            )
        elif step.type == "pair_waves":
            checkpoints.append(
                f"{prefix} uses hidden `uid` lineage to form matched student pairs and preserves "
                "that lineage so the final aggregate can count contributing students exactly."
            )
        elif step.type == "bucket_school_size":
            checkpoints.append(
                f"{prefix} computes distinct-student counts per school to assign bands, but those "
                "intermediate counts are not exposed as results and are not themselves suppressed."
            )
        elif step.type == "aggregate":
            checkpoints.append(
                f"{prefix} computes the exact distinct-student `N` for every metric cell and blanks "
                f"cells where `N < {min_n}`."
            )

    return checkpoints


def render_examples_markdown(df: pd.DataFrame, *, min_n: int = MIN_N_FOR_DOCS) -> str:
    lines = [
        "# Query Builder",
        "",
        "This document is generated from the executable query examples in "
        "`api/src/glow_api/query_examples.py`.",
        "",
        f"All results below were generated against the shared test fixture dataset with `min_n = {min_n}`.",
        "",
        "The query interface is a suppression-aware plan DSL with these steps:",
        "",
        "1. `filter`",
        "2. `derive_score`",
        "3. `pair_waves`",
        "4. `bucket_school_size`",
        "5. `aggregate`",
        "",
        "Every plan finishes with `aggregate`, which is the only point where values are materialized.",
    ]

    for example in query_examples():
        result = execute_example(example, df, min_n=min_n)
        values_df = parse_result_csv(result.csv)
        counts_df = parse_result_csv(result.count_csv)

        lines.extend(
            [
                "",
                f"## {example.title}",
                "",
                f"Question: {example.question}",
                "",
                "Plan:",
                "",
                "```json",
                json.dumps(example.plan.model_dump(mode="json", exclude_none=True), indent=2),
                "```",
                "",
                "Values:",
                "",
                _render_markdown_table(values_df),
                "",
                "Contributing distinct-student counts:",
                "",
                _render_markdown_table(counts_df),
                "",
                f"Suppressions: `{json.dumps(result.suppressions, sort_keys=True)}`",
                "",
                "Suppression checkpoints:",
            ]
        )
        lines.extend([f"- {item}" for item in describe_suppression_checkpoints(example.plan, min_n=min_n)])
        lines.extend(
            [
                "",
                "Execution provenance:",
            ]
        )
        lines.extend([f"- {item}" for item in result.provenance])

    lines.append("")
    return "\n".join(lines)
