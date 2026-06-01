# Step 3: Rewrite Query Execution Around Period Slices

## Goal

Replace the current wave-first, single-variable, neighbor-oriented query engine with a period-oriented multi-variable query engine. This step must follow TDD.

## Scope

- Backend only
- Query execution, suppression, response formatting, deterministic ordering, and `/query` ETags

## Files in Scope

- `api/tests/test_query.py`
- `api/tests/test_blanket_suppression.py`
- `api/tests/test_contract_examples.py`
- `api/src/glow_api/routers/query.py`
- `api/src/glow_api/models.py`
- `api/src/glow_api/blanket_suppression.py` or its replacement
- `api/src/glow_api/contract_examples.py`
- `api/src/glow_api/utils.py` or a new query-execution helper module

## TDD Requirement

Implement this step as a sequence of small failing tests for each behavior: variable selection, aggregation, suppression, totals, metadata, and caching.

## Work

1. Add failing tests for selecting variables by:
   - repeated `v`
   - repeated `variable_prefix`
   - union of both
   - all-variables default
2. Add failing tests for response organization.
   - top-level `query`, `dimensions`, `periods`, `variables`
   - period-organized variable slices
   - missing variable-period entries meaning not collected or not applicable
3. Add failing tests for per-variable deduplication.
   - latest non-null value per `uid` per school-period bucket
4. Add failing tests for totals computed from deduped item values.
5. Add failing tests for period-scoped blanket suppression.
   - `small-n`
   - `incompatible-version`
   - suppression independent inside each period
6. Add failing tests for period-level notes.
   - `values-rescaled` on affected periods only
7. Add failing tests for deterministic ordering and ETag behavior.
   - canonical query hash
   - salt from `(ODK ETag || dataset-updated timestamp) + API version`
   - `If-None-Match` leading to `304`
8. Replace the old query execution path with the new period-slice engine.

## Completion Criteria

- The `/query` endpoint is multi-variable and period-oriented.
- Query results no longer use the old focus-school plus neighbors plus waves contract.
- Deduplication occurs per variable using the agreed latest-non-null rule.
- Derived totals are calculated from deduped constituent item values.
- Suppression is evaluated independently per period and uses only `small-n` and `incompatible-version`.
- `values-rescaled` appears only on affected period slices.
- Query responses are deterministically ordered.
- `ETag` and `If-None-Match` behavior works for `/query` using the agreed canonical query salt recipe.
