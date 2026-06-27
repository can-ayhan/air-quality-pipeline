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

## Running a load

```
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
docker compose up -d                                      # PostgreSQL on localhost:5435
python -m airquality ingest --from 2026-04-20 --to 2026-04-21
```

`ingest` creates the raw tables if they are missing, then loads the stations and sensors
of the configured cities (`config/cities.yml`), their hourly results and the hourly weather
for the given days. Loading the same days again updates the rows in place.

## Models

```
pip install -e ".[dbt]"
dbt build --project-dir dbt --profiles-dir dbt
```

`dbt build` loads the reference data, builds the staging views and the marts, and runs the tests
in between: a failed test on staging holds back the marts that read from it.

| Layer | Schema | What |
|---|---|---|
| raw | `raw` | what the APIs returned, one table per endpoint |
| staging | `staging` | one view per raw table: renamed columns, UTC next to the published CET time |
| marts | `marts` | `dim_station`, `fct_measurement_hourly` (incremental), `fct_weather_hourly`, `mart_station_daily` |

## Running it every day

```
docker compose up -d --build        # PostgreSQL and Airflow, UI on http://localhost:8080
```

The DAG `air_quality_daily` runs at 06:00 UTC, loads the previous day from both APIs and then
runs `dbt build`. It is paused when first created; switch it on in the UI.

## Status

Work in progress: steps 1 to 3 are done, 4 runs but has no retries or alerts yet.
