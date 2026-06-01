# Step 2: Build Submission Normalization Layer

## Goal

Introduce a normalization layer ahead of query execution that derives observed periods, prepares per-submission metadata, and exposes variable-ready analytic records. This step must follow TDD.

## Scope

- Backend only
- Data loading and in-memory normalization
- No dashboard changes

## Files in Scope

- `api/tests/test_data.py`
- `api/tests/conftest.py`
- `api/tests/mock_odk.py`
- `api/src/glow_api/data.py`
- `api/src/glow_api/settings.py`
- `api/src/glow_api/models.py` if internal normalized models are kept there
- New normalization module(s), likely under `api/src/glow_api/`

## TDD Requirement

Use explicit red-green-refactor cycles for each normalization rule. Do not batch the whole normalization layer and test it only at the end.

## Work

1. Add failing tests for period derivation from submission `createdAt`.
   - convert into deployment timezone first
   - then apply configured cutoff rule
2. Add failing tests for observed-period behavior.
   - observed periods only
   - suppressed periods still count as observed periods later in query output
   - unobserved current periods are not invented
3. Add failing tests for preserving edited submissions in their original period.
4. Add failing tests for carrying enough submission metadata forward for later version comparison and deduplication.
5. Implement a normalized representation that can be consumed by query execution without re-deriving periods repeatedly.
6. Ensure derived totals can later be computed from deduped item values rather than raw rows.

## Completion Criteria

- All normalization rules above are covered by tests that were written before the implementation.
- The datastore exposes normalized period information based on `createdAt`, not `wave`.
- Period derivation is timezone-aware and cutoff-aware.
- Edited submissions retain their original period anchor.
- The normalization layer makes observed periods discoverable without query execution having to rescan raw timestamps.
- The implementation does not depend on the old wave-first API contract.
