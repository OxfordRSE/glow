# Student Identity considerations

It is absolutely vital to be able to link student data longitudinally.
For this to be possible, we have to uniquely and persistently identify students across multiple timepoints.

## Student input

Identifiers may need to be entered by students. 
If this is the case, they need to be simple and verifiable. 

They could perhaps be verified by matching with some kind of check-word (e.g. a simple concrete noun)
so we can immediately recognise if an identifier is not expected.

Ideally, we issue individual links for each student with the identifier pre-completed.

## Anonymity

Insofar as possible, student identifiers should not be clearly linked to the students (e.g. a name)
anywhere in the system.

At minimum, student identifiers will not appear in the ODK data - we will hash them first.

## Internationalization

Any process of normalizing student identifiers must be robust across languages and regions. 
It's no good using a case-insensitive comparison in latin-alphabet countries if we can't implement
the same normalization in arabic countries, for example. 

## Implementation plan candidates

### School generated identifier

The obvious choice for identifying students is the school's own internal identifier. 
For some schools this will be a student number, or a student code (e.g. initials plus a number),
while for others it might just be the student's name. 

- How do we normalize identifiers consistently worldwide?
- What happens if a student's identifier changes? Is that acceptable data loss?
- Does this risk ingesting identifying information e.g. a name?
- Schools already manage this identifier and are familiar with it
- How do we check students enter it correctly?

### Centrally generated identifier

We could maintain a list of central identifiers which are assigned to students by schools.
Schools would supply us with a number of students they wanted to generate ids for, 
we would generate those ids, and then the school would store those ids against student 
identifiers in their own records.

- Requires schools to persistently manage an additional document
- We probably still have to store a list of submitted ids somewhere, which means it's still in our stack if compromised
- Not sure there are clear advantages over using school identifiers directly

## Id Integrity plan candidates

### Check-word

We could take a list of all student identifiers the school wants to collect data for and 
associate each one with a simple concrete noun (e.g. bear, door, guitar) and ask the student to 
enter both their id and their check-word. 
If the id and check-word don't match, we'd tell them so, otherwise we'd generate a questionnaire for them
and forward them to it.

This would work as a separate web service that would sit in front of the data collection platform.
Students would visit it and, when their id and check-word are okay'd, be forwarded to the actual 
data collection link. 

This probably wouldn't work with ODK Collect. 

### School-assigned prefilled links

We could ask the school to tell us which student identifiers they wanted to collect data for and
return a collection of individualised web links: one for each student. 

This would be a separate service as isolated as possible from the rest of the ODK and API stack,
although realistically probably part of the same. 
To be useful, we'd have to record the ids and links.

## Circles

- We don't want the school to have to manage a 3rd party identifier
- So schools should send us their own internal identifiers
- But those can be sensitive information so we don't really want to store them
- But if we don't store them we can't guarantee them
- So we ask the school to store them
- But we don't want the school to have to manage a 3rd party identifier


