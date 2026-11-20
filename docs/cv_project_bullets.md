# CV project bullets

- Built a Python pipeline that fetched and validated live Open-Meteo forecasts for five Romanian cities, saving two replayable JSON snapshots with 30 forecast entries across 20 distinct city-days.
- Loaded 10 city snapshots into Snowflake VARIANT and transformed them into 20 city-day forecasts with SQL; verified zero duplicate RAW keys after replay and correct precedence for all 10 overlapping city-days.
