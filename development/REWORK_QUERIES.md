# Rework Query Interface

We will move away from a display of focus school data + neighboring schools data.
Instead, we will present data for the focus school and provide context in terms of mean and standard deviation
calculated from the whole eligible sample (including the school).

We'll also take the opportunity to move from a school and wave-led structure to a variable-led structure.

## Things to change

### Remove neighbour code

- Neighbor calculation helper script
- Neighbor metadata columns
- Neighbor query calculations
- Neighbor query data
- Neighbor data representation in Dashboard and Storybook

### Restructure query output

Queries will now be responded to in a new shape:

```typescript
type FilteredQueryString = string; // QueryString syle encoding e.g. sex=M&age=13&wave=2
type FilteredQueryResponse = {
    data?: Record<FilteredQueryString, {
        value: number | null;
        n?: number;
        n_all: number;
        mean_all: number | null;
        sd_all: number | null;
    }>;
    metadata: {
        limits?: {
            min?: number;
            max?: number;
        };
        suppression?: {
            reason: string;
        }
    };
}
// Indexed by variable name
type QueryResponse = Record<string, FilteredQueryResponse>
```

Examples:

```json
{
  "bw_wbeing_1": {
    "metadata": {
      "limits": {
        "max": 5
      }
    },
    "data": {
      "sex=M&age=13&wave=1": {
        "value": 3.8,
        "n": 12,
        "n_all": 1342,
        "mean_all": 2.5,
        "sd_all": 1.2
      },
      "sex=M&age=13&wave=2": {
        "value": 3.9,
        "n": 12,
        "n_all": 1342,
        "mean_all": 2.8,
        "sd_all": 1.1
      },
      "sex=F&age=13&wave=1": {
        "value": 2.9,
        "n": 17,
        "n_all": 1412,
        "mean_all": 2.9,
        "sd_all": 0.8
      },
      "sex=F&age=13&wave=2": {
        "value": 2.4,
        "n": 14,
        "n_all": 1400,
        "mean_all": 2.7,
        "sd_all": 1.0
      }
    }
  },
  "bw_wbeing_23": {
    "metadata": {
      "suppression": {
        "reason": "too-few-records"
      }
    }
  }
}
```

The Dashboard can thus figure out which facets each data value applies to. 
Through simple statistics, the Dashboard can also figure out how to produce weighted means for any aggregation 
it desires, e.g. calculating mean/sd for all sex=M records by combining the two sex=M records and weighting
the value by n and the mean_all/sd_all by n_all.

### Calcuation of `_all` variables

These are essentially given by not applying school={focus school} as a filter. 
So we know `n_all` will always be >= `n`, and we know that if `n` is great enough to avoid suppression
then `n_all` is also. 

### Suppression

Suppression continues to obey the 'if any then all' rule.
We can naively calculate the response we're about to send out, then simply check in each facet for n < N_MIN. 
If that's the case, that entire variable can be replaced with 
`{ "metadata": { "suppression": { "reason": "too-few-records" } } }`.

There's a potential problem with overly-keen suppression triggering because of incomplete data collection during a wave.
E.g. if only 3 records for a school are registered in a wave, ALL data for ANY query about that school will 
be suppressed. 
If this turns out to be an issue we'll address it later.

## Dashboard queries in

Queries will now send a target school, a list of variables, and an optional set of grouping variables.
The backend doesn't distinguish between filters and groupings 
('if any then all' allows us to treat everything as a grouping, 
always send back all groups, and let the recipient choose what to keep).

## Dashboard display

The Dashboard will always send the target school, at least one variable, and at least 'wave' as a grouping variable.
We'll move to have fewer pages and each page shows a whole subscale of questions (so sends multiple varaibles)
on one graph, and then shows the total on a second graph. 

Grand means and SDs are plotted for each `value` datapoint for reference.


## General queries

The API will support general queries where there's no target school included.
In these cases, `value` and `n` will be undefined, and values will instead reflect the entire sample.

## Concerns

Have we reintroduced a potential for differencing attacks with exposing Ns and facets in this way? 
The numbers will be high, but potentially still arithmetically exploitable.
