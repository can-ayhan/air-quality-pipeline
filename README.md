# Air Quality Data Pipeline

Daily pipeline that loads hourly air-quality readings and weather for Polish cities into a PostgreSQL warehouse.

- Air quality: the public API of the Chief Inspectorate of Environmental Protection (GIOŚ), hourly measurements per station
- Weather: Open-Meteo, hourly temperature, humidity, wind, precipitation and pressure per city

## Plan

1. Clients for the two APIs
2. Raw tables in PostgreSQL, loads that can be repeated for the same day
3. dbt on top: staging, marts, tests
4. Airflow to run it every day and to backfill
5. CI

## Status

Work in progress.
