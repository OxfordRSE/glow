# Persistent student identifiers

We need to solidify a way to identify students.
Our current plan is to ask the schools to use whatever mechanism they use internally. 

This may be insufficient where schools e.g. only use a student's name.

## Data entry

Students must not be required to enter their identifier themselves, or, if they are,
they must be given a simple check-word to verify their identifier is entered correctly.

There's probably not support for doing this with ODK, so we may need to run another 
small service on the container to generate id-checkword pairs,
verify the ids, and link them to the questionnaire responses.

The linkage could be accomplished via prefilled links if ODK supports them (i.e. with queryparams),
otherwise we can use the ODK API to generate a unique web link for the student to use.

We may need a hidden internal identifier that can reliably disambiguate between two 
students with the same 'identifier': e.g. a school uses student names and has two 
"Jane Smith" students in different yeargroups - we'd know which Jane Smith was logging in
because she'd give us her checkword, but we'd need to keep that disambiugation in the questionnaire response data.
