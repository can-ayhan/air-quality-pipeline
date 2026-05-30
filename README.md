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

So far the dbt project declares the raw tables as sources and builds one staging view on each.

## Status

Work in progress: steps 1 and 2 are done, 3 has started.
