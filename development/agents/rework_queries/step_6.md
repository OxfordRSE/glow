# Step 6: Rewrite Dashboard Bootstrap and Query Flow

## Goal

Move the dashboard off `/admin/me`, `/schools`, waves, and neighbor comparisons, and onto the new `/me`, `/dimensions`, and period-organized `/query` contract. This step must follow TDD.

## Scope

- Frontend primarily
- Dashboard routing, bootstrap state, API client, chart/table shaping, Storybook and mock contracts

## Files in Scope

- `dashboard/src/lib/api.ts`
- `dashboard/src/lib/stores.ts`
- `dashboard/src/routes/[locale]/+layout.svelte`
- `dashboard/src/routes/[locale]/login/+page.svelte`
- `dashboard/src/routes/[locale]/+page.svelte`
- `dashboard/src/lib/chartUtils.ts`
- `dashboard/src/lib/csvUtils.ts`
- `dashboard/src/lib/i18n/en.ts`
- `dashboard/src/lib/mocks/contractExamplesData.ts`
- `dashboard/src/lib/mocks/handlersFromExamples.ts`
- `dashboard/src/lib/mocks/contractExamples.test.ts`
- `dashboard/src/stories/pages/DashboardExamples.stories.ts`
- Component stories that assume the old query shape

## TDD Requirement

Use failing frontend tests and Storybook interaction tests to drive the rewrite. For this repo, Storybook contract examples and interaction tests count as part of the TDD loop and should be updated before the final implementation settles.

## Contract-Coherence Requirement

The current frontend-backend coherence mechanism must be preserved.

Today the dashboard does not hand-maintain its API fixtures independently. Instead:

- API-owned contract examples are generated into `dashboard/src/lib/mocks/contractExamplesData.ts`
- `dashboard/src/lib/mocks/contractExamples.ts` treats those generated examples as the registry
- `dashboard/src/lib/mocks/handlersFromExamples.ts` builds MSW handlers from those examples and uses them in Storybook/tests

This is the project's current single-source-of-truth path for keeping frontend mocks aligned with backend contracts, and the query rework must continue to use it.

Do not replace this with hand-written frontend-only fixtures for the main API surfaces. If the API contracts change, the backend examples and the generated dashboard example data must change with them, and Storybook/MSW must continue consuming those generated examples.

## Work

1. Add failing tests or stories for guest bootstrap.
   - anonymous users are not redirected away from the dashboard
   - `/me` anonymous state is handled explicitly
2. Add failing tests or stories for authenticated bootstrap.
   - school picker sourced from `/me`
   - variable/dimension discovery sourced from `/dimensions`
3. Add failing tests for `GET /query` URL construction.
   - repeated `v`
   - repeated `d`
   - repeated `variable_prefix`
   - omitted variable selectors meaning all variables
4. Rewrite page state around period-organized multi-variable results.
5. Replace wave-based and neighbor-based rendering assumptions in charts and tables.
6. Update localization strings and empty/loading/error states for anonymous and school-scoped flows.
7. Update the example-generation and mock-consumption path for the new API surfaces.
   - backend contract examples must cover `/me`, `/dimensions`, and `GET /query`
   - generated dashboard example data must be refreshed from backend-owned examples
   - Storybook/MSW handlers must continue to read those generated examples rather than bespoke fixtures

## Completion Criteria

- Unauthenticated users can load the dashboard and issue dataset-scoped queries.
- Authenticated users bootstrap from `/me`, not `/admin/me`.
- Query discovery comes from `/dimensions`, not `/schools.query_options`.
- Dashboard query URLs use repeated params for `v`, `d`, and `variable_prefix`.
- Page logic understands period slices, missing period entries, suppression metadata, and period-level notes.
- Storybook examples and mock contracts match the new API surfaces.
- The dashboard continues to derive its main mocked API responses from backend-owned contract examples, not parallel hand-maintained frontend fixtures.
