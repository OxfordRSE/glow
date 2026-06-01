# Step 4: Replace Discovery and Identity Endpoints

## Goal

Ship the new `/me` and `/dimensions` endpoints and remove `/schools` as the query-discovery API. This step aligns the backend surface with the agreed anonymous-query and school-scoped discovery model.

## Scope

- Backend primarily
- Small frontend contract fixture updates if needed to keep examples compiling

## Files in Scope

- `api/tests/test_api.py`
- `api/tests/test_contract_examples.py`
- `api/src/glow_api/main.py`
- `api/src/glow_api/auth.py`
- `api/src/glow_api/models.py`
- `api/src/glow_api/routers/admin.py`
- `api/src/glow_api/routers/schools.py`
- New router files, likely `api/src/glow_api/routers/me.py` and `api/src/glow_api/routers/dimensions.py`
- `api/src/glow_api/database.py` if school summaries need helper queries

## Work

1. Implement `GET /me` with optional authentication.
   - no token -> anonymous payload
   - bad token -> `401`
   - good token -> authenticated payload with school summaries
2. Implement `GET /dimensions`.
   - public dataset-scoped discovery
   - auth-checked school-scoped discovery via `school_id`
3. Remove query-discovery concerns from `/schools`.
4. Decide whether `/schools` is removed immediately or left temporarily unreachable from the dashboard while downstream cleanup lands.
5. Update contract examples and OpenAPI-visible models.

## Completion Criteria

- `/me` returns the agreed discriminated union with `kind`.
- `/dimensions` returns only variable keys and dimension definitions, with optional `school_id` echo.
- School-scoped `/dimensions` calls enforce school access.
- `/schools` is no longer the canonical query-discovery endpoint.
- Backend contract examples no longer describe `query_options` as the discovery model.
