# Mock Data

This note captures the agreed direction for making GLOW's development and demo data substantially messier and more realistic.

## Goal

We want seeded development data that break clean assumptions.

- Not every school collects in the same years.
- Not every school uses the same questionnaire version.
- A school-period may contain mixed questionnaire versions.
- Not every form carries the same metadata.
- Not every student has every expected form in a period.
- Different forms may reuse the same field name.
- Periods are derived from submission timestamps, not from an explicit wave field.

The main use cases are:

- local development
- seeded demo environments
- smoke testing of real ODK seeding flows
- exposing incorrect assumptions before they appear in production

We will continue to use small curated checked-in datasets for most automated tests.

## Agreed High-Level Dataset

- Use a larger generated base dataset with about 20 schools.
- Assign school wave patterns deterministically, with two donor-only schools reserved for creating one 4-wave recipient school and one 5-wave recipient school.
- The five waves map to five academic years: `2020-2021` through `2024-2025`.
- `wave` exists only in the generation and transformation pipeline.
- The actual analytic periods come from rewritten ODK `createdAt` timestamps.
- Include a few submissions around the `31 Aug` / `1 Sep` boundary to exercise period derivation.

## Canonical Base Generator

The clean base dataset should come from `glow-dummies`, not from handwritten CSV authoring.

Canonical source:

- `../glow-dummies/examples/glow_model.toml`

This canonical base model generates:

- 3 clean source waves for every school
- full BeeWell v2 item coverage
- standard demographics and year-group progression
- PHQ-9 for every student in the base dataset
- one extra synthetic overlap-control item in the base dataset

The overlap-control item is intentionally generated under a disambiguated base column name:

- `phq_overlap_bw_wbeing_1`

This is necessary because the `glow-dummies` base output is a wide table, so a true raw-name collision would overwrite one column with the other. The later transformation step renames this field into raw `bw_wbeing_1` only in the PHQ-9 form output.

## Base Questionnaire Design

The canonical base model uses questionnaire definitions inside `glow-dummies` itself.

- BeeWell v2 comes from the existing full BeeWell questionnaire set.
- PHQ-9 uses the built-in 9-item depression instrument.
- A one-item synthetic PHQ overlap-control questionnaire is added to create a later raw field-name clash.

The PHQ overlap-control item is not pretending to be a real clinical instrument. Its purpose is to create a repeatable, documented collision case in transformed per-form seed data.

## Repeatable Base Generation

Example command:

```bash
cd ../glow-dummies
julia --project=. bin/glow_dummies \
  --config examples/glow_model.toml \
  --seed 42 \
  > ../glow/data/glow_base.csv
```

The output is a clean wide CSV intended to be transformed, not seeded directly into ODK.

Wave-pattern allocation for the standard output schools:

- 5 schools collect in waves `1,2,3`
- 5 schools collect in waves `2,3,4`
- 4 schools collect in waves `3,4,5`
- 1 school collects in waves `1,2,5`
- 1 school collects in waves `1,3,5`
- 1 school collects in waves `1,2,3,4`
- 1 school collects in waves `1,2,3,4,5`

Additionally:

- 2 generated schools are treated as donor-only schools in the transformation step
- those donor schools are dropped from the final seeded output
- their generated rows are deterministically reused to provide the extra wave material for the 4-wave and 5-wave recipient schools

## Forms

We will model four form surfaces.

1. `bewell_questionnaire`
2. `phq9_questionnaire`
3. `demographics_questionnaire`
4. Historical BeWell `v1` as an older version of `bewell_questionnaire`

The current full BeWell form is treated as `v2`.

## Shared Metadata Rules

Every form submission should carry:

- `uid`
- `school`

The `uid` should embed school identity, for example `schoolslug_studentid`, so that a student identifier is unique across schools.

The BeWell and PHQ-9 forms should not carry:

- `wave`
- `class`
- `yearGroup`
- `d_*`

The demographics form should carry:

- `uid`
- `school`
- `yearGroup`
- `d_age`
- `d_sex`
- `d_ethnicity`
- `d_sexualOrientation`
- `d_genderIdentity`

`yearGroup` advances over time per student. We should intentionally include a few students who repeat a year and a few who skip a year.

## BeWell Versioning

We agreed that the older BeWell version should be used mainly in early collection.

- Most schools that have wave 1 should use BeWell `v1` there.
- One school should use BeWell `v1` in all of its collected waves.
- One school should use BeWell `v1` only in its middle collected wave.
- At least one school-period should contain a mix of BeWell `v1` and `v2` submissions.

The old BeWell `v1` should be representative rather than exhaustive.

- Some overlapping items should be unchanged.
- Some overlapping items should be shifted.
- Some overlapping items should be rescaled.
- Some questions present in `v2` should be absent in `v1`.

Recommended concrete shape for `v1`:

- Keep `bw_selfest_*` unchanged as a compatibility control.
- Shift `bw_wbeing_*` from `0..5` in `v2` to `1..6` in `v1`.
- Rescale `bw_stress_*` from `0..5` in `v2` to `0..3` in `v1`.
- Drop a large set of later question groups in `v1`, for example `bw_future_*`, `bw_mhcontact_*`, `bw_kooth_1`, and one or more other multi-item sections.

Both BeWell XMLs should be checked into the repo so version-specific metadata can be extracted from real form definitions.

## PHQ-9

PHQ-9 should be a separate ODK form.

- Include `phq9_1` through `phq9_9`.
- Support a derived `phq9_total` in the analytic data.
- Use PHQ-9 only for a subset of school-waves.
- Include some school-waves that start late or stop early.

To force name-clash handling, the PHQ-9 form should also contain one extra numeric field that deliberately reuses a BeWell variable name.

Recommended clash field:

- `bw_wbeing_1`

This field exists only to verify that the API does not silently merge variables from different forms.

## Demographics Authority

Demographics should be authoritative for:

- `yearGroup`
- all `d_*` fields

The other forms should not carry those fields at all.

## Analytic Data Model

The raw loaded data should start as separate submissions in one stacked table, one row per submission.

That stacked table should include form identity, for example via a synthetic column such as `__xmlFormId` added at fetch time.

After that, GLOW should materialize a single analytic row per:

- `uid`
- `school`
- `period_id`

Shared dimensions can stay unprefixed:

- `uid`
- `school`
- `period_id`
- `yearGroup`
- `d_*`

Questionnaire variables exposed by the API should be namespaced as:

- `xmlFormId__field`

Examples:

- `bewell_questionnaire__bw_wbeing_1`
- `phq9_questionnaire__phq9_1`
- `phq9_questionnaire__bw_wbeing_1`

This namespacing is required so two forms can reuse the same field name safely.

## Missingness and Messiness Defaults

We want moderate messiness, not total chaos.

Recommended defaults:

- one mixed-version school-period at about `70/30`
- a small percentage of missing PHQ-9 submissions where PHQ-9 is expected
- a small percentage of missing demographics submissions
- a few year repeats
- a few year skips
- a handful of submissions placed at period-boundary dates

The transformation script should be deterministic from a seed.

## Generation and Seeding Pipeline

Recommended pipeline:

1. Generate a larger base dataset.
2. Deterministically assign schools to wave patterns.
3. Split the base rows into per-form submission rows.
4. Remove form-inappropriate fields from each form.
5. Assign BeWell version usage by school and period.
6. Introduce controlled missingness and version mixing.
7. Seed forms into ODK Central.
8. Rewrite submission timestamps so each submission lands in the intended academic year bucket.
9. Refresh the API and verify observed periods and variables.

The large dev/demo dataset should be generated then transformed, not mostly hand-authored.

## Deterministic Transformation Step

The transformation step is implemented in:

- `scripts/odk/transform_mock_data.py`

It takes the canonical wide base CSV and emits:

- `bewell_questionnaire_v1.csv`
- `bewell_questionnaire_v2.csv`
- `phq9_questionnaire.csv`
- `demographics_questionnaire.csv`
- `manifest.csv`
- `school_plans.csv`
- `summary.json`

Example command:

```bash
python scripts/odk/transform_mock_data.py \
  --input data/glow_base.csv \
  --output-dir data/mock_seed \
  --forms-dir odk-forms
```

The transformation derives form field lists from the checked-in XMLs, so the script follows the real forms instead of re-declaring them.

## Transformation Rules

The current deterministic transformation applies these documented manipulations.

### School-level assignments

- schools are sorted deterministically
- each school gets a deterministic `school_code`
- the last two generated schools are reserved as donor-only schools
- the remaining output schools are assigned target waves using the adjusted pattern split above
- each school gets a deterministic PHQ coverage mode from:
  - `all`
  - `first_two`
  - `last_two`
  - `middle_only`
  - `none`

### Donor-school reuse

- one donor-only school provides extra rows for the 4-wave recipient school
- one donor-only school provides extra rows for the 5-wave recipient school
- this reuse is deterministic and captured in `school_plans.csv` as explicit `wave_mappings`
- donor schools do not appear as final output schools in the transformed seed data

### BeeWell version assignments

- school 1 is all-v1
- school 2 is v1 only in its middle collected wave
- school 3 has a mixed earliest school-period with about `70/30` v1/v2 allocation
- all other schools use v1 only in target wave 1 and v2 otherwise

### Student-level participation changes

- some students are dropped entirely
- some join late by missing their first source wave
- some leave early by missing their last source wave
- some skip the middle source wave
- additional synthetic late joiners are introduced by cloning donor trajectories from later source waves under new UIDs

### Demographic progression changes

- transformed UIDs are prefixed with school identity
- `yearGroup` is adjusted deterministically for a small number of students so some repeat and some skip a year

### Form-level missingness

- PHQ-9 is omitted for some student-periods even when the school uses PHQ-9
- demographics is omitted for some student-periods

### Timestamp planning

- every manifest row gets an intended `target_created_at`
- most dates are mid-academic-year
- a deterministic small subset are placed on `1 Sep` or `31 Aug` boundary dates

### Cross-form collision handling

- the canonical base column `phq_overlap_bw_wbeing_1` is renamed to raw `bw_wbeing_1` only in `phq9_questionnaire.csv`
- this creates the intended raw field-name clash between BeeWell and PHQ-9 in the final per-form seed data

## BeWell v1 Derivation

BeeWell v1 rows are not guessed manually; they are built by transforming BeeWell v2 source rows into the field set defined by `odk-forms/bewell_questionnaire_v1.xml`.

Current rules:

- retain only the fields present in the v1 XML
- shift `bw_wbeing_*` by `+1`
- rescale `bw_stress_*` from the base `0..4` style values onto `0..3`
- omit all later sections that do not exist in the v1 XML

If the v1 XML changes, the transform script will pick up the new field list automatically.

## ODK Seeding Strategy

Because mixed old/new BeWell submissions may depend on what ODK Central validates against the currently active form version, the safe fallback is phase-based seeding.

Recommended seeding order:

1. Upload BeWell `v1` and seed the rows that should use `v1`.
2. Upload BeWell `v2` as the next version of the same `xmlFormId` and seed the `v2` rows.
3. Upload and seed `phq9_questionnaire`.
4. Upload and seed `demographics_questionnaire`.
5. Rewrite timestamps for all seeded submissions using instance IDs.

The local ODK timestamp rewrite targets are now confirmed in the running schema: `submissions.createdAt`, `submissions.updatedAt`, and `submission_defs.createdAt`. That rewrite should be implemented as a demo/dev data-management script keyed by instance ID, not as a manual database operation.

## Concrete Implementation Phases

### 1. Forms and metadata sources

- Check in BeWell `v1` XML with `xmlFormId="bewell_questionnaire"`.
- Keep BeWell `v2` XML current at `odk-forms/bewell_questionnaire_v2.xml`, also with `xmlFormId="bewell_questionnaire"`.
- Add PHQ-9 XML.
- Add demographics XML.
- Keep enough source material checked in that metadata extraction is reproducible.

This is the right starting point because it gives us concrete form surfaces, concrete question ranges, and a real target for transformed mock data.

### 2. Data transformation scripts

- Add a script that transforms generated base data into per-form CSVs or manifests.
- Make school-pattern assignment deterministic.
- Make year progression deterministic.
- Make missingness deterministic.
- Emit a manifest that records each submission's intended form, version, wave, and target period.

This step should produce the target dataset shape before we change the API.

### 3. Seeding and timestamp rewriting

- Extend the ODK seeding flow to seed multiple forms.
- Support seeding BeWell in versioned phases.
- Add a demo/dev timestamp rewrite script keyed by instance ID.
- Integrate the new steps into `dev-init.sh`.

### 4. Inspect and stabilize the seeded target dataset

- Verify what ODK `submissions.csv` exports actually look like for each form.
- Verify how `__version`, `createdAt`, and other system fields appear after phase-based seeding.
- Verify that mixed BeWell versions are preserved as intended.
- Verify that timestamp rewriting lands submissions in the expected academic-year buckets.
- Treat this exported data shape as the target contract for the API ingestion refactor.

### 5. API multi-form support

- Replace the single-form configuration with a form registry or form list.
- Fetch submissions for multiple `xmlFormId`s.
- Add a form-id column to each fetched frame before concatenation.
- Fetch metadata per form.
- Fetch version-specific metadata for BeWell `v1` and `v2`.

### 6. Analytic materialization

- Stop relying on per-variable deduplication as the only mechanism.
- Materialize one analytic row per `uid` + `school` + `period_id`.
- Use demographics as the authoritative source for `yearGroup` and `d_*`.
- Namespace questionnaire variables as `xmlFormId__field`.
- Recompute derived totals after the analytic row is assembled.

### 7. Query-layer updates

- Update variable discovery to expose namespaced variables.
- Extend numeric variable whitelisting beyond `bw_*` so `phq9_*` is queryable.
- Make version compatibility checks form-aware and version-aware.
- Preserve per-period notes for rescaling and mixed versions.

### 8. Dashboard and contract updates

- Make sure dashboard variable discovery does not assume BeWell-only variables.
- Decide how namespaced variables should be labelled in the UI.
- Update contract examples if API response shapes change.

### 9. Tests and fixtures

- Keep small curated fixtures for most unit and API tests.
- Add small fixtures that exercise:
- multi-form loading
- namespaced variable collisions
- mixed BeWell versions in one period
- missing demographics
- missing PHQ-9
- period-boundary timestamps
- Use the large generated dataset for dev/demo and manual QA rather than for most checked-in tests.

## Success Criteria

We are done when:

- the API can ingest multiple forms into one analytic dataset
- clashing variable names from different forms stay distinct
- PHQ-9 variables are queryable end-to-end
- BeWell version differences are surfaced from real metadata
- school periods are derived from manipulated timestamps across five academic years
- seeded demo data visibly contain irregular school participation and form usage patterns
- curated tests cover the new assumptions we are deliberately breaking
