# Dashboard features

## Anonymous login

We'll allow anonymous login to the dashboard (the default page won't redirect to the login screen anymore). 
Instead, you'll see the page with no selected school and have the option to send the same queries
which will return means and SDs for the whole sample. 

### Components

- Login button on the top bar when not logged in
- Automated logout if not authenticated
- School selection moved to the top bar
- School selection removed for users with only one school: shows only the school name
- Queries sent without a focus school when logged out
- Data displayed in the focus school slot in the graphs is the grand mean

## Full reports

The Dashboard will show entire subsections of the questionnaire by default.
We will add support for a view that shows _all_ data broken down by the desired grouping variables.

This will need a nice print view (we should have a nice print view anyway!).

## Multiple questionnaires

We will add support for handling multiple questionnaires.
This may require updates to the backend.
