# Query Builder

This document is generated from the executable query examples in `api/src/glow_api/query_examples.py`.

All results below were generated against the shared test fixture dataset with `min_n = 5`.

The query interface is a suppression-aware plan DSL with these steps:

1. `filter`
2. `derive_score`
3. `pair_waves`
4. `bucket_school_size`
5. `aggregate`

Every plan finishes with `aggregate`, which is the only point where values are materialized.

## Count students by school

Question: How many distinct students are in scope for each school?

Plan:

```json
{
  "steps": [
    {
      "type": "aggregate",
      "group_by": [
        "school"
      ],
      "metrics": [
        {
          "kind": "count_students"
        }
      ]
    }
  ]
}
```

Values:

| school | student_n |
| ------ | --------- |
| Focus School Academy  | 5.0       |
| Neighbouring School   | 5.0       |

Contributing distinct-student counts:

| school | student_n |
| ------ | --------- |
| Focus School Academy  | 5.0       |
| Neighbouring School   | 5.0       |

Suppressions: `{}`

Suppression checkpoints:
- Before step execution, user scope filters are applied and `uid` is retained internally so distinct-student counts can be computed later without making identifiers public.
- Step 1 `aggregate`: computes the exact distinct-student `N` for every metric cell and blanks cells where `N < 5`.

Execution provenance:
- Aggregated metrics with suppression based on contributing distinct-student N.

## Mean derived BeeWell score by school

Question: What is the mean derived `bw_wbeing_total` for each school?

Plan:

```json
{
  "steps": [
    {
      "type": "derive_score",
      "score": "bw_wbeing_total"
    },
    {
      "type": "aggregate",
      "group_by": [
        "school"
      ],
      "metrics": [
        {
          "kind": "mean",
          "column": "bw_wbeing_total"
        }
      ]
    }
  ]
}
```

Values:

| school | bw_wbeing_total |
| ------ | --------------- |
| Focus School Academy  | 9.8             |
| Neighbouring School   | 8.8             |

Contributing distinct-student counts:

| school | bw_wbeing_total |
| ------ | --------------- |
| Focus School Academy  | 5.0             |
| Neighbouring School   | 5.0             |

Suppressions: `{}`

Suppression checkpoints:
- Before step execution, user scope filters are applied and `uid` is retained internally so distinct-student counts can be computed later without making identifiers public.
- Step 1 `derive_score`: derives an approved measure on row-level data; suppression still waits for the terminal aggregate.
- Step 2 `aggregate`: computes the exact distinct-student `N` for every metric cell and blanks cells where `N < 5`.

Execution provenance:
- Derived bw_wbeing_total from available BeeWell wellbeing item columns.
- Aggregated metrics with suppression based on contributing distinct-student N.

## Mean within-student change after a baseline threshold

Question: Among students whose baseline `bw_wbeing_total` is at least 3, what is the mean change from wave 1 to wave 2 by school?

Plan:

```json
{
  "steps": [
    {
      "type": "derive_score",
      "score": "bw_wbeing_total"
    },
    {
      "type": "pair_waves",
      "from_wave": "1",
      "to_wave": "2",
      "measures": [
        "bw_wbeing_total"
      ]
    },
    {
      "type": "filter",
      "column": "baseline_bw_wbeing_total",
      "op": "gte",
      "value": 3
    },
    {
      "type": "aggregate",
      "group_by": [
        "school"
      ],
      "metrics": [
        {
          "kind": "mean",
          "column": "change_bw_wbeing_total",
          "as_column": "avg_change"
        },
        {
          "kind": "count_students"
        }
      ]
    }
  ]
}
```

Values:

| school | avg_change | student_n |
| ------ | ---------- | --------- |
| Focus School Academy  | 0.8        | 5.0       |

Contributing distinct-student counts:

| school | avg_change | student_n |
| ------ | ---------- | --------- |
| Focus School Academy  | 5.0        | 5.0       |

Suppressions: `{}`

Suppression checkpoints:
- Before step execution, user scope filters are applied and `uid` is retained internally so distinct-student counts can be computed later without making identifiers public.
- Step 1 `derive_score`: derives an approved measure on row-level data; suppression still waits for the terminal aggregate.
- Step 2 `pair_waves`: uses hidden `uid` lineage to form matched student pairs and preserves that lineage so the final aggregate can count contributing students exactly.
- Step 3 `filter`: validates that `baseline_bw_wbeing_total` is public at this stage; it narrows the cohort but does not publish a value or apply `min_n` yet.
- Step 4 `aggregate`: computes the exact distinct-student `N` for every metric cell and blanks cells where `N < 5`.

Execution provenance:
- Derived bw_wbeing_total from available BeeWell wellbeing item columns.
- Paired waves 1 -> 2 for bw_wbeing_total.
- Filtered baseline_bw_wbeing_total gte 3.
- Aggregated metrics with suppression based on contributing distinct-student N.

## Mean score after school-size bucketing

Question: What is the mean `bw_wbeing_total` by year group after bucketing schools by distinct-student participation?

Plan:

```json
{
  "steps": [
    {
      "type": "derive_score",
      "score": "bw_wbeing_total"
    },
    {
      "type": "bucket_school_size",
      "output_column": "school_size_bucket",
      "bands": [
        {
          "label": "small",
          "min_students": 0,
          "max_students": 4
        },
        {
          "label": "medium",
          "min_students": 5,
          "max_students": 9
        },
        {
          "label": "large",
          "min_students": 10
        }
      ]
    },
    {
      "type": "aggregate",
      "group_by": [
        "school_size_bucket",
        "yearGroup"
      ],
      "metrics": [
        {
          "kind": "mean",
          "column": "bw_wbeing_total"
        }
      ]
    }
  ]
}
```

Values:

| school_size_bucket | yearGroup | bw_wbeing_total |
| ------------------ | --------- | --------------- |
| medium             | 7         | 9.8             |
| medium             | 8         | 8.8             |

Contributing distinct-student counts:

| school_size_bucket | yearGroup | bw_wbeing_total |
| ------------------ | --------- | --------------- |
| medium             | 7         | 5.0             |
| medium             | 8         | 5.0             |

Suppressions: `{}`

Suppression checkpoints:
- Before step execution, user scope filters are applied and `uid` is retained internally so distinct-student counts can be computed later without making identifiers public.
- Step 1 `derive_score`: derives an approved measure on row-level data; suppression still waits for the terminal aggregate.
- Step 2 `bucket_school_size`: computes distinct-student counts per school to assign bands, but those intermediate counts are not exposed as results and are not themselves suppressed.
- Step 3 `aggregate`: computes the exact distinct-student `N` for every metric cell and blanks cells where `N < 5`.

Execution provenance:
- Derived bw_wbeing_total from available BeeWell wellbeing item columns.
- Bucketed schools into school_size_bucket using distinct-student counts.
- Aggregated metrics with suppression based on contributing distinct-student N.

## Suppressed small longitudinal cohort

Question: How many students had a baseline `bw_wbeing_total` above 10 when matched from wave 1 to wave 2, by school?

Plan:

```json
{
  "steps": [
    {
      "type": "derive_score",
      "score": "bw_wbeing_total"
    },
    {
      "type": "pair_waves",
      "from_wave": "1",
      "to_wave": "2",
      "measures": [
        "bw_wbeing_total"
      ]
    },
    {
      "type": "filter",
      "column": "baseline_bw_wbeing_total",
      "op": "gt",
      "value": 10
    },
    {
      "type": "aggregate",
      "group_by": [
        "school"
      ],
      "metrics": [
        {
          "kind": "count_students"
        }
      ]
    }
  ]
}
```

Values:

| school | student_n |
| ------ | --------- |
| Focus School Academy  |           |

Contributing distinct-student counts:

| school | student_n |
| ------ | --------- |
| Focus School Academy  |           |

Suppressions: `{"student_n": {"0": "<5"}}`

Suppression checkpoints:
- Before step execution, user scope filters are applied and `uid` is retained internally so distinct-student counts can be computed later without making identifiers public.
- Step 1 `derive_score`: derives an approved measure on row-level data; suppression still waits for the terminal aggregate.
- Step 2 `pair_waves`: uses hidden `uid` lineage to form matched student pairs and preserves that lineage so the final aggregate can count contributing students exactly.
- Step 3 `filter`: validates that `baseline_bw_wbeing_total` is public at this stage; it narrows the cohort but does not publish a value or apply `min_n` yet.
- Step 4 `aggregate`: computes the exact distinct-student `N` for every metric cell and blanks cells where `N < 5`.

Execution provenance:
- Derived bw_wbeing_total from available BeeWell wellbeing item columns.
- Paired waves 1 -> 2 for bw_wbeing_total.
- Filtered baseline_bw_wbeing_total gt 10.
- Aggregated metrics with suppression based on contributing distinct-student N.
