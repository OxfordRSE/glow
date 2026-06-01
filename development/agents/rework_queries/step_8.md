# Step 8: Final Verification and Release Readiness

## Goal

Confirm that the rework meets the repo's definition of done across API and dashboard, and leave the tree in a coherent state for review or follow-on implementation.

## Scope

- Backend and frontend
- Verification, formatting, final example alignment, release-readiness checks

## Files in Scope

- All files changed in steps 1 through 7
- Any CI or config files touched only if needed to make the new test/build path pass

## Work

1. Run API verification.
   - relevant tests during development
   - full API test suite at the end
   - Ruff formatting and cleanup
2. Run dashboard verification.
   - `npm run test`
   - `npx tsc`
   - `npm run build`
3. Confirm Storybook/mock contract examples exactly match the backend return surfaces.
4. Review the changed files for:
   - unused imports
   - dead helpers
   - stale comments referring to waves or neighbors
   - duplicated query-normalization logic
5. Record any deliberate follow-up work that is out of scope for this rework.

## Completion Criteria

- API tests pass.
- Ruff formatting is clean.
- Dashboard tests pass.
- `npx tsc` is clean.
- Dashboard build succeeds.
- Storybook mock handlers and contract examples match the relevant backend surfaces.
- There are no known remaining code paths serving the old query interface.
