# Step 5: Extend ODK Ingestion for Version-Aware Comparison

## Goal

Teach ingestion to retrieve and retain the ODK metadata needed for historical form-version comparison and period-safe rescaling decisions. This step must follow TDD.

## Scope

- Backend only
- ODK client, metadata fetch, form-version lookup, compatibility logic

## Files in Scope

- `api/tests/test_data.py`
- `api/tests/test_query.py`
- `api/tests/conftest.py`
- `api/tests/mock_odk.py`
- `api/src/glow_api/odk_client.py`
- `api/src/glow_api/data.py`
- `api/src/glow_api/settings.py`
- New helper module(s) for version compatibility or form-definition caching

## TDD Requirement

Write failing tests for each ODK metadata and compatibility rule before implementation. In particular, do not add rescaling logic without tests that prove both the rescaled and fail-closed cases.

## Work

1. Add failing tests for extracting submission metadata needed for:
   - `createdAt`
   - form version identity
   - any other submission fields required to map a response row to its form definition
2. Add failing tests for retrieving historical form definitions by version.
3. Add failing tests for version compatibility outcomes.
   - compatible unchanged limits
   - trivially compatible narrower-to-wider limits
   - trivially compatible limit shifts (e.g. 0-indexed to 1-indexed; 1-5 to -2-+2)
   - incompatible forms causing `incompatible-version`
4. Implement caching or reuse so form-definition retrieval does not become an accidental per-row network operation. All forms are fetched when their data are fetched.
5. Feed the resulting version metadata into the normalization/query layers built in steps 2 and 3.

## Completion Criteria

- ODK ingestion can identify the form version associated with analytic records.
- Historical form definitions can be retrieved for the versions needed by tests.
- Compatibility logic distinguishes:
  - comparable values
  - rescaled values
  - suppress-with-`incompatible-version` cases
- The implementation fails closed when comparability cannot be established.
- Query-layer tests can consume real version metadata from ingestion rather than only synthetic fixtures.
