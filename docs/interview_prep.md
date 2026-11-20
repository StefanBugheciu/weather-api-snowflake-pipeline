# Weather pipeline interview preparation

## A 30-second walkthrough

I fetch three daily forecasts for five Romanian cities from Open-Meteo.
Python checks the dates, units, and measurements and saves a JSON
snapshot. The Snowflake loader uses a city-and-start-date key to merge
the original JSON into RAW. An analytics view expands the arrays into
daily rows for temperature and precipitation comparisons.

## Questions to practice

- **Why timeout and retry?** A timeout bounds a connection or read attempt.
  I retry transient errors, including rate limits and selected 5xx responses.
  I validate every response before publishing the snapshot.
- **Why keep JSON?** I can inspect the source response and replay the same
  payload without calling the API. VARIANT preserves the nested structure.
- **What is the grain?** RAW holds one payload per city and forecast start
  date. The view exposes one row per city and forecast date.
- **How do you join the arrays?** FLATTEN returns the date and its index.
  GET uses that index to retrieve corresponding values from the metric arrays.
- **What happens on reruns?** The Snowflake MERGE uses the same key and
  compares capture times. The view independently resolves overlapping
  forecast windows. Standard Snowflake primary keys are informational,
  so this demo uses serial loads.
- **How would you prove which overlapping forecast won?** Load two
  captures with consecutive start dates. For city-days where both
  captures provide a forecast, compare the view's selected start date
  with the maximum start date present in RAW.
- **What did you verify live?** Snowflake held 10 RAW snapshots and 20
  analytics rows. Replaying a capture left its five rows unchanged.
  All 10 overlapping city-days selected the latest start date. The
  rollback path was tested with a mock connection.
