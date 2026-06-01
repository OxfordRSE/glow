# Step 1: Lock Contracts and Canonical Query Rules

## Goal

Freeze the external API contracts before deeper implementation work starts. This step should make the agreed `/me`, `/dimensions`, and `GET /query` shapes executable as tests and examples, and should define the canonical query normalization used for response echoes and ETags.

## Scope

- Backend only
- No dashboard behavior changes yet beyond any contract fixtures needed to keep examples aligned

## Files in Scope

- `api/tests/test_api.py`
- `api/tests/test_query.py`
- `api/tests/test_contract_examples.py`
- `api/src/glow_api/models.py`
- `api/src/glow_api/routers/query.py`
- `api/src/glow_api/contract_examples.py`
- `api/src/glow_api/main.py`
- `api/src/glow_api/utils.py` or a new canonical-query helper module
- New router files if introduced for `/me` and `/dimensions`

## Work

1. Add or update API tests for:
   - `GET /me` anonymous response
   - `GET /me` authenticated response
   - invalid-token `401` behavior for `/me`
   - public `GET /dimensions`
   - protected `GET /dimensions?school_id=...`
   - `GET /query` parsing for repeated `v`, repeated `d`, and repeated `variable_prefix`
   - union semantics when both `v` and `variable_prefix` are supplied
   - default-to-all-variables behavior when neither is supplied
2. Define the request normalization rules in one place.
   - sort and dedupe variables, dimensions, and prefixes
   - normalize omitted `d` to an empty list
   - expand the canonical query model so it can be echoed in responses
3. Update API contract examples to the new endpoint shapes.
4. Decide where the canonical query utility lives and make tests use it indirectly through the public API.

## Completion Criteria

- Tests exist for all agreed endpoint contracts and query-parameter rules.
- There is one clear canonical-query normalization path, not duplicated ad hoc across routers.
- Contract examples reflect the new `/me`, `/dimensions`, and `GET /query` agreements.
- Query normalization covers:
  - `school_id`
  - repeated `v`
  - repeated `d`
  - repeated `variable_prefix`
  - all-variables default
  - deterministic ordering for later ETag use
- No new query behavior is still described only in markdown; it is represented in tests or examples.
