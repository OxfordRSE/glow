# Step 7: Remove Legacy Wave and Neighbor Paths

## Goal

Delete the old wave-first, neighbor-first, and `/schools`-driven query-discovery code so the codebase does not carry two mental models at once.

## Scope

- Backend and frontend
- Cleanup, dead-code removal, fixture replacement, story replacement

## Files in Scope

- `api/src/glow_api/dashboard_query_options.py`
- `api/src/glow_api/blanket_suppression.py` if superseded
- `api/src/glow_api/routers/schools.py`
- `api/src/glow_api/models.py`
- `api/src/glow_api/contract_examples.py`
- `api/tests/test_dashboard_query_options.py`
- `api/tests/test_blanket_suppression.py`
- `dashboard/src/routes/[locale]/+page.svelte`
- `dashboard/src/lib/chartUtils.ts`
- `dashboard/src/lib/mocks/contractExamplesData.ts`
- `dashboard/src/stories/pages/DashboardExamples.stories.ts`
- Any remaining files referring to neighbors, waves as query input, or `query_options`

## Work

1. Remove or replace tests that only make sense for the old discovery and neighbor model.
2. Remove stale models and response types from API and dashboard code.
3. Delete dead helper code that only existed to support wave or neighbor queries.
4. Replace contract examples and stories that still mirror the old shape.
5. Remove unused imports and orphaned helpers in every touched file.

## Completion Criteria

- No user-facing code still depends on the old wave-first query contract.
- No dashboard bootstrap path depends on `/schools` for query discovery.
- No API contract examples still show focus-school plus neighbors results.
- Files touched in earlier steps no longer carry unused compatibility scaffolding for the removed model.
- Search results for old concepts such as `query_options`, `include_neighbors`, and wave-based query inputs are either gone or intentionally limited to migration notes.
