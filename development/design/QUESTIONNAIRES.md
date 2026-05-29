# Questionnaires

We need to establish what kinds of questionnaires will be used and how.

## Metadata

The more metadata we can extract from a questionnaire the more detailed insights we can provide to users.

We need a good way of embedding metadata into questionnaires, or otherwise associating it with them.

To the extent that the XML forms allow, we could use that, bearing in mind many users will probably want to 
define forms in XLSX format. 

The ideal solution is:

- machine-readable 
- embedded in the questionnaire
- detailed
- easy for questionnaire writers to include
- able to handle multiple different versions of questionnaires

## Questionnaire updates/changes

We need the system to handle questionnaire updates and changes well.

We need to be able to track data across waves, so we need to be able to track changes to questions.

These data should be readily surfaced by ODK's responses, and we can perhaps save a list of questionnaire
versions that can be used as a filter by the dashboard (perhaps too advanced).

In any case, where there are multiple questionnaire versions, we can display a note to that effect,
perhaps saying how many responses were to each version.

### Anti-assumptions

We must not assume:

- All schools will use the same version of the questionnaire
- All questionnaires for a school in a given wave will use the same version
- Schools will not go back to using an old questionnaire version
