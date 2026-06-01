# Rework Queries Plan

## Purpose

This directory breaks the query-interface rework into concrete implementation steps.

The goal of the rework is to replace the old wave-first, neighbor-oriented query model with a period-oriented, multi-variable query interface that works for anonymous dataset queries and authorized school-scoped queries.

These step files are intended to be executed in order unless a later step explicitly depends only on already-landed infrastructure.

## Step Order

1. `step_1.md`
   - Lock external contracts and canonical query rules.
2. `step_2.md`
   - Build the submission normalization layer.
3. `step_3.md`
   - Rewrite query execution around period slices.
4. `step_4.md`
   - Replace discovery and identity endpoints.
5. `step_5.md`
   - Extend ODK ingestion for version-aware comparison.
6. `step_6.md`
   - Rewrite dashboard bootstrap and query flow.
7. `step_7.md`
   - Remove legacy wave and neighbor code paths.
8. `step_8.md`
   - Run final verification and release-readiness checks.

## Dependency Notes

- Step 1 should land first. It fixes the external contract and canonical query rules that later steps depend on.
- Step 2 provides normalized data structures needed by steps 3 and 5.
- Step 3 depends on step 2 and is the main backend query-engine rewrite.
- Step 4 can begin once the new contracts are stable, but it should align with step 3's response shapes.
- Step 5 feeds version-compatibility metadata into the normalization and query layers built in steps 2 and 3.
- Step 6 should wait until the backend contracts used by the dashboard are stable enough to avoid churn.
- Step 7 is cleanup and should happen only after the new paths are working.
- Step 8 is the final integrated verification pass.

## TDD Requirements

The project rules in `AGENTS.md` require test-driven development for API changes and strong verification for dashboard changes.

In this rework, explicit red-green-refactor cycles are required for:

- `step_2.md`
- `step_3.md`
- `step_5.md`
- `step_6.md`

For those steps, tests or stories should be written first and observed to fail before implementation is added.

## Contract Summary

### `/me`

- `GET /me`
- no token: anonymous response
- invalid or expired token: `401`
- valid token: authenticated response with school summaries

Current intended shape:

```ts
type MeResponse =
  | { kind: "anonymous" }
  | {
      kind: "authenticated";
      id: number;
      username: string;
      is_admin: boolean;
      schools: { id: number; name: string }[];
    };
```

### `/dimensions`

- `GET /dimensions`
- optional `school_id` query param
- dataset scope is public
- school scope requires authorization for that school

Current intended shape:

```ts
type DimensionsResponse = {
  school_id?: number;
  variables: { key: string }[];
  dimensions: { key: string; type: "string" | "number" }[];
};
```

### `/query`

- `GET /query`
- optional `school_id`
- repeated `v` for variable selection
- repeated `d` for dimension selection
- repeated `variable_prefix` for prefix-based bulk selection
- omit `d` to mean no dimensions
- omit both `v` and `variable_prefix` to mean all variables
- if both `v` and `variable_prefix` are supplied, union them

## Glossary

### canonical query

The normalized internal form of a query request after sorting, deduping, and applying defaults. It is used for response echoes, deterministic behavior, and ETag generation.

### dataset-scoped query

A query with no `school_id`. It operates over the whole accessible public dataset and is allowed anonymously.

### school-scoped query

A query with `school_id` supplied. It targets one focus school and requires that the caller be authorized for that school.

### period

A collection-time bucket derived by the API from submission timestamps rather than taken from a user-supplied wave field.

### `period_id`

The identifier for a derived collection period. It is not treated as a normal query dimension and has special status in suppression logic.

### observed period

A period that had at least one submission in the dataset. Top-level `periods` should include observed periods only, even if results within a period are later suppressed.

### open or current period

A currently active collection window according to deployment configuration. An empty current period is not automatically included unless it is also an observed period.

### period boundary

The rule that maps a timestamp into a period. It is defined by deployment-specific timezone and cutoff configuration.

### dimension

A grouping axis requested by the client, such as sex or ethnicity. The rework uses `dimensions` terminology consistently instead of the old aggregation/filter split.

### variable

A numeric measure that can be queried, such as an item score or derived total score.

### variable prefix

A query selector that expands to all variables whose names start with the supplied prefix. This is intended to support bulk retrieval of subscales or related item families.

### variable slice

The portion of a query response associated with one variable, typically containing metadata plus period-organized results.

### period slice

The portion of a variable response associated with a single period. It may contain data cells or suppression metadata.

### cell

One observed aggregate result for a variable within a period and a specific set of non-period coordinates.

### coordinates

The scalar values, or `null`, that identify where a cell sits across the requested non-period dimensions.

### focus school

The school identified by `school_id` in a school-scoped query. General dataset-scoped queries do not have a focus school.

### sample

The whole analytic comparison set returned alongside focus-school values in school-scoped queries, or by itself in dataset-scoped queries.

### deduplication

The per-variable rule for reducing multiple submissions to one effective value per `uid` per school-period bucket.

### latest non-null rule

The agreed deduplication rule: for each variable, keep the latest non-null value for each `uid` within each school-period bucket.

### derived total

A computed total score built from constituent item values. Under the rework it must be calculated from deduped item values, not directly from raw submissions.

### suppression

The process of withholding results to protect privacy when a query would expose too small an `n`, or when values cannot safely be compared across versions.

### blanket suppression

The any-to-all rule already used by the project: if any cell in the relevant grouped result is too small, all cells in that grouped result are suppressed.

### privileged suppression boundary

The special rule that suppression is evaluated independently inside each `period_id`, rather than across all periods together.

### suppression reason

The machine-readable reason returned when a period slice cannot expose data. The agreed initial reasons are `small-n` and `incompatible-version`.

### `small-n`

Suppression reason used when blanket suppression hides a result because a cell would reveal too small a cohort.

### `incompatible-version`

Suppression reason used when questionnaire values in a period cannot be safely unified across versions.

### `values-rescaled`

A machine-readable note indicating that compatible values in a period were linearly rescaled from a narrower declared range to a wider one.

### question version

The questionnaire form version associated with a submission or effective analytic record.

### `question_versions` counts

Metadata describing how many effective deduped records for a variable came from each questionnaire version.

### historical form definition

The questionnaire XML or equivalent metadata for a specific past form version, used to determine comparability and rescaling rules.

### normalization layer

The backend layer that prepares raw ODK submissions for query execution by deriving periods, carrying version metadata, and exposing consistent analytic records.

### createdAt anchor

The rule that a submission's original `createdAt` timestamp determines its period assignment, even if the submission is edited later.

### canonical ordering

A deterministic ordering of query components and response structures so that equal inputs produce equal outputs.

### ETag salt

The non-query part of the `/query` ETag seed. In this rework it is the dataset-version marker `(ODK ETag || dataset-updated timestamp)` plus the Glow API version.

### dataset-version marker

The value representing which dataset snapshot a query ran against. Prefer the upstream ODK ETag when available, otherwise fall back to the tracked dataset-updated timestamp.

### contract example

An example payload used to keep documented and mocked API shapes aligned across backend tests and dashboard stories.

## Source Documents

- `development/REWORK_QUERIES.md`
- `development/agents/REWORK_QUERIES.md`
- `development/DASHBOARD.md`
- `AGENTS.md`
