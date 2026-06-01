# Step 9: Claude Follow-Up Fixes

## Purpose

This file records the specific places where `feature/period-query-rework-with-frontend` still falls short of the rework design described in `README.md` and `step_1.md` through `step_8.md`.

The goal is not to restart the design. The goal is to finish the existing design properly.

## Highest-Priority Gaps

1. The backend query engine does not yet implement the agreed deduplication and derived-total rules.
2. Version-aware comparison is only partially wired and currently does not fail closed in the intended way.
3. The dashboard is still partly bootstrapped from `/schools` instead of fully switching to `/me` and `/dimensions`.
4. Old `/schools` and `query_options` discovery assumptions are still present in frontend mocks, stories, and API helpers.

## Step 2 Fixes: Normalization Layer

The current normalization layer in `api/src/glow_api/normalization.py` is too thin for the design.

- `normalize_submissions()` only adds `period_id` on demand inside the query router. The design wanted normalization to become a reusable datastore layer rather than a per-request patch-up step.
- `get_observed_periods()` still rescans the normalized frame at query time. Step 2 asked for observed periods to be made discoverable without query execution having to rescan raw timestamps. The cachable things (data frame including deduplication and derived variables, data collection period lists, form metadata) should all be cached during the data loading step.
- The implementation does not create a clearer normalized analytic representation carrying the metadata later steps need for deduplication and version comparison.
- The period model is still effectively an academic-year bucket in `derive_period_id()`. Re-check that against the intended deployment-specific period boundary. If the product requirement is truly academic-year based then the docs should say so explicitly. If not, this logic needs to be brought back in line with the design.

## Step 3 Fixes: Query Execution

The biggest backend gaps are in `api/src/glow_api/query_execution.py`.

- `deduplicate_submissions()` groups by `uid` and `period_id` only. The agreed rule was per variable, per `uid`, per school-period bucket. Dataset-scoped queries can currently collapse records from different schools if the same `uid` appears in more than one school.
- Derived totals are not recomputed from deduped constituent item values. The current path queries precomputed totals as ordinary variables, which violates the agreed rule in Step 3.
- `question_versions` exists in the response model but is never populated in the actual period slices.
- `values-rescaled` notes can be emitted, but no rescaling is actually applied. `apply_rescaling` is imported and then not used.
- Version checks are only attempted when `form_metadata` is passed, but the router currently never passes real form metadata into `execute_query()`.
- The implementation suppresses incompatible periods, but it does not yet demonstrate the intended fail-closed path based on ingestion-provided historical form definitions.
- The ETag logic is present, but the salt currently uses only `dfwl.metadata.get("_etag", "unknown")` from `api/src/glow_api/routers/query.py`. The design called for `(ODK ETag || dataset-updated timestamp) + API version`, so the fallback dataset-version marker still needs to be implemented explicitly.

## Step 4 Fixes: Discovery and Identity Endpoints

`/me` and `/dimensions` are mostly present, but they still need tightening.

- `api/src/glow_api/routers/dimensions.py` hard-codes all dimensions as `type="string"`. The design requires `"string" | "number"` based on the actual dimension type.
- `/dimensions` currently calls `datastore.to_frozen()` twice in one request path. That is minor, but the endpoint should be cleaned up while fixing the more important issues.
- `/schools` is still actively used by the dashboard as a school-list bootstrap endpoint. Even if `/schools` remains for administration, it is still functionally part of dashboard bootstrap today.

## Step 5 Fixes: Version-Aware Comparison

The branch creates `api/src/glow_api/version_compatibility.py`, but it is still below the Step 5 design.

- `check_version_compatibility()` is currently permissive: any differing numeric range becomes rescalable. The design was narrower than that and required explicit coverage for safe cases and fail-closed incompatible cases.
- The implementation is not yet backed by real historical form-definition retrieval from ingestion. `api/src/glow_api/data.py` fetches form metadata, but the query path is still not consuming version metadata end to end.
- There is no strong evidence yet that all needed forms are fetched when their data are fetched, rather than compatibility remaining a query-time optional extra.
- Query-layer tests should consume ingestion-fed version metadata, not only synthetic `form_metadata` dicts supplied to the engine.

## Step 6 Fixes: Dashboard Bootstrap and Query Flow

The frontend is still not fully aligned with the design.

- `dashboard/src/routes/[locale]/+page.svelte` still calls `listSchools()` and uses `/schools` as part of authenticated bootstrap. Step 6 explicitly called for the school picker to be sourced from `/me`.
- The same page fetches `/dimensions` only once on mount. Changing `selectedSchoolId` does not currently trigger a refetch of school-scoped dimensions.
- The page supports explicit variable selection only. It does not expose `variable_prefix` selection, and it does not exercise the all-variables default path where both `v` and `variable_prefix` are omitted.
- `dashboard/src/lib/chartUtils.ts` drops information when dimensions are present in multi-period queries. `newQueryToChartData()` takes only the first cell per period for multi-period charts instead of rendering grouped coordinates coherently.
- `newQueryToChartData()` and `newQueryToCSV()` do not make much use of period-level notes or `question_versions`, so the UI still under-represents the richer response contract.
- Anonymous dataset-scoped querying is supported at a basic level, but the frontend still looks structurally closer to a simplified explore page than to a fully finished replacement of the previous dashboard flow.

## Step 7 Fixes: Remove Legacy Wave and Neighbor Paths

This is the biggest remaining cleanup area.

- `dashboard/src/lib/api.ts` still contains old `/schools` helpers and comments describing `query_options` as the discovery path.
- `dashboard/src/lib/mocks/contractExamplesData.ts` still includes `/schools` examples and embedded `query_options` payloads.
- `dashboard/src/lib/mocks/handlersFromExamples.ts` still wires `GET /schools` into the main mock path.
- `dashboard/src/stories/pages/DashboardExamples.stories.ts` still configures the page around `GET /schools` examples.
- The old discovery model is therefore still alive in mocks and stories, even though the runtime page moved toward `/me` and `/dimensions`.

## Step 8 Fixes: Verification and Release Readiness

Before this branch can be considered done against the rework plan, it still needs a stronger final pass.

- Add verification that school changes in the dashboard refresh dimensions and query behavior correctly.
- Add tests that prove deduplication is per `uid` per school-period bucket, not just per `uid` per period.
- Add tests that prove totals are computed from deduped item values rather than queried from precomputed raw totals.
- Add tests that prove real ingestion-fed version metadata can cause either rescaling or `incompatible-version` suppression.
- Remove remaining `/schools` mock and story dependencies so the frontend-backend coherence path is based on the new contract surfaces instead of parallel legacy fixtures.

## Concrete Next Changes

1. Move normalization and observed-period derivation into `DataStore` so query execution consumes a stable normalized dataset instead of normalizing ad hoc in the router.
2. Rewrite `deduplicate_submissions()` to group by `uid`, school, and `period_id`, and to drop all-null buckets for the target variable.
3. Recompute derived totals from deduped constituent item values inside the query engine.
4. Thread real form metadata from ingestion into query execution and populate `question_versions` in the response.
5. Apply actual value rescaling when compatibility rules allow it, and fail closed otherwise.
6. Source the dashboard school picker from `/me` and refetch `/dimensions` whenever school scope changes.
7. Replace the remaining `/schools` and `query_options` mock/story path with the new `/me`, `/dimensions`, and `GET /query` examples.

## Acceptance Bar For The Follow-Up

This branch should not be considered complete until all of the following are true.

- No dashboard bootstrap path depends on `/schools` for query discovery.
- Query execution follows the agreed latest-non-null per-variable dedup rule inside school-period buckets.
- Derived totals are computed from deduped items.
- Version-aware comparison is driven by ingestion metadata and can both rescale safely and suppress incompatibly.
- Frontend mocks and stories consume only the new contract surfaces for the reworked query flow.
