# Air Quality Data Pipeline

A daily pipeline that loads hourly air-quality readings and weather for seven Polish cities
into a PostgreSQL warehouse, models them with dbt and refuses to publish a load that fails its tests.

- **Air quality**: the public API of the Chief Inspectorate of Environmental Protection (GIOŚ),
  hourly results per station for PM10, PM2.5, NO2, O3, SO2, CO and benzene
- **Weather**: Open-Meteo, hourly temperature, humidity, wind, precipitation and pressure per city
- **Cities**: Warszawa, Kraków, Wrocław, Łódź, Poznań, Gdańsk, Katowice (`config/cities.yml`)

Both APIs are free and need no key.

```
 GIOŚ API ─────┐                 ┌────────────── dbt ───────────────┐
               ├─ ingest ─> raw ─┤ staging ─> tests ─> marts ─> tests ├─> station-level analysis
 Open-Meteo ───┘  (Python)       └──────────────────────────────────┘
        └──────────── Airflow: every day at 06:00 UTC, retries, alerts, backfills ────────────┘
```

| | |
|---|---|
| Ingestion | Python 3.12, `requests`, `psycopg` |
| Warehouse | PostgreSQL 16 |
| Models and tests | dbt-core 1.11 with dbt-postgres |
| Orchestration | Apache Airflow 3.2 |
| Packaging | Docker Compose: PostgreSQL and an Airflow image with the pipeline in its own virtualenv |
| CI | GitHub Actions: lint, Python tests, `dbt build`, DAG tests |

## Try it

The models and their tests can be tried without calling the APIs. One day of two Warsaw sensors
is saved in `tests/fixtures` and goes through the same ingest code as a real load:

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,dbt]"
docker compose up -d warehouse                    # PostgreSQL on localhost:5435
python tests/load_sample.py
dbt build --project-dir dbt --profiles-dir dbt    # 72 nodes: 8 models, 1 seed, 61 data tests, 2 unit tests
```

A real load, for any range of days:

```
python -m airquality ingest --from 2026-07-01 --to 2026-07-07
dbt build --project-dir dbt --profiles-dir dbt
```

A day of all seven cities is 146 sensors and takes three to five minutes, nearly all of it waiting
for GIOŚ. A longer range costs little more, because one request covers up to a year: January to
June 2026 loaded in under six minutes.

The whole thing on a schedule:

```
docker compose up -d --build                      # Airflow UI on http://localhost:8080
```

The DAG `air_quality_daily` is paused when first created; switch it on in the UI.
Settings are in `.env.example`; the defaults work as they are.

## Ingestion

`src/airquality` has a client per API and a loader that writes four raw tables.

- **GIOŚ** (`gios.py`): stations, the sensors of each station, and results per sensor from the
  archive endpoint. Responses are JSON-LD with Polish keys and are paged; the client follows the
  pages and retries timeouts, `429` and `5xx` with a growing pause.
- **Open-Meteo** (`openmeteo.py`): one point per city. Recent days come from the forecast endpoint,
  days older than about three months from the archive endpoint; the client picks by the age of the range.
- **Loads can be repeated.** Every write is an upsert on the table's key. A result that is already
  stored with the same value is left alone, so `loaded_at` means "last changed" and reloading a day
  reports how many results were new or different.
- **An empty answer is a failure.** If every request succeeds and none has a result for the last
  day asked for, the command exits with 1 instead of reporting a successful load of nothing.

## Models

| Layer | Schema | Contents |
|---|---|---|
| raw | `raw` | what the APIs returned: `gios_station`, `gios_sensor`, `gios_measurement`, `openmeteo_hourly` |
| staging | `staging` | one view per raw table: renamed columns, a UTC timestamp next to the published CET one |
| reference | `reference` | `pollutant_limits` (seed): unit, plausible bounds and WHO guideline per pollutant |
| marts | `marts` | `dim_station`, `fct_measurement_hourly`, `fct_weather_hourly`, `mart_station_daily` |

- `fct_measurement_hourly`: one row per sensor and hour. Incremental on `loaded_at` rather than on
  the measurement time, so a backfill or a corrected day is picked up and replaces its own rows.
- `mart_station_daily`: one row per station, pollutant and day with the mean, the maximum and the
  highest 8-hour mean, whether the day has enough hours to count (18 of 24), whether it is above the
  WHO short-term guideline, and the day's weather in the station's city. Ozone is judged on the
  8-hour mean, the others on the daily mean.

GIOŚ publishes hourly results in CET all year, without daylight saving. The models keep both
clocks: UTC to join the weather, CET because the day a result counts towards is the CET day.

## Data quality

`dbt build` runs the tests of a model before anything that reads from it. A failed test on the
staging layer holds the marts back, so they stay as they were after the last good load.

| What | Where |
|---|---|
| Nulls | keys and timestamps in sources, staging and marts; values in the hourly fact |
| Duplicates | station, sensor, sensor-hour, city-hour and station-pollutant-day keys |
| Out-of-range values | every result against the plausible bounds of its pollutant; weather against physical bounds; coordinates inside Poland; 1 to 24 hours in a day |
| Broken references | sensors without a station, results without a sensor, pollutants missing from the reference data |
| Time | no timestamps in the future; a unit test on the CET to UTC shift in winter, on the clock-change day and in summer |
| Granularity | hourly results only (GIOŚ also returns daily filter samples under the same pollutant) |
| Aggregation | a unit test of the daily mart on three made-up station-days; the hours in the mart must add up to the rows of the fact |

The plausible bounds are not air-quality limits. They bound what an analyser can report at all, so
a value outside them is a unit or parsing error. The case they are there for is real: the GIOŚ
archive endpoint publishes carbon monoxide in mg/m³ and the current-data endpoint publishes the
same sensors in µg/m³.

What a blocked load looks like, with a CO result of 412 put into the raw table by hand:

```
44 of 72 FAIL 1 assert_values_are_plausible .................................... [FAIL 1 in 0.06s]
55 of 72 SKIP relation marts.fct_measurement_hourly ............................ [SKIP]
66 of 72 SKIP relation marts.mart_station_daily ................................ [SKIP]
Done. PASS=53 WARN=0 ERROR=1 SKIP=18 NO-OP=0 TOTAL=72
```

`tests/test_pipeline.py` repeats this on every push.

## Orchestration

`dags/air_quality_daily.py`: both ingests, then `dbt build`. Every day at 06:00 UTC.

- **Incremental.** A run belongs to one day, the day its data interval starts on. It also asks
  again for the two days before: a request covers a range at the cost of one, unchanged rows are
  left alone, and results published late are picked up.
- **Retries.** The ingest tasks are retried three times, with a pause that starts at two minutes
  and doubles each time. The dbt build is not retried: a failed test fails again on the same data
  and should be looked at.
- **Alerts.** A task that fails for good posts one message (task, run, attempt, error, link to the
  log) to the webhook in `ALERT_WEBHOOK_URL`. Without it the message goes to the task log.
- **Backfills.** One run per day, oldest first, one task instance at a time so that a backfill
  neither multiplies the requests to the APIs nor runs two dbt builds on the same tables.

One day, from the UI ("Trigger", then *Day to load*) or the command line:

```
docker compose exec airflow airflow dags trigger air_quality_daily -c '{"target_date": "2026-07-08"}'
```

A range of days:

```
docker compose exec airflow airflow backfill create --dag-id air_quality_daily \
    --from-date 2026-07-13 --to-date 2026-07-15T06:00
```

The run for a day has the logical date 06:00 UTC of that day, so an end given as a bare date stops
one day short: `--to-date 2026-07-15` creates the runs for the 13th and the 14th.

The Compose file runs Airflow as one `standalone` container next to PostgreSQL, which is enough
for one DAG on one machine. The pipeline code and dbt are installed in a separate virtualenv in the
image, so their dependencies never have to agree with Airflow's; the DAG only starts commands in it.

## CI

Every push runs three jobs in GitHub Actions (`.github/workflows/ci.yml`):

- **Lint and tests**: ruff, then the Python tests against a PostgreSQL service
- **dbt build**: the saved API responses loaded through the ingest code, every model built and every
  dbt test run, then a check that an out-of-range result stops the marts and that a reloaded day
  replaces its rows
- **Airflow DAG**: the DAG imported in Airflow 3.2.1, its wiring, retries, alert callback and the
  commands it renders for a scheduled run and for a chosen day

## What six months of data show

1 January to 30 June 2026: 504,545 hourly results from 119 sensors at 34 stations, 21,243
station-days. The queries are in `analysis/station_queries.sql`.

Share of station-days above the WHO short-term guideline (days with at least 18 measured hours):

| Pollutant | Station-days | Above the guideline |
|---|---:|---:|
| PM2.5 | 4,087 | 48.4 % |
| NO2 | 4,439 | 44.5 % |
| PM10 | 5,160 | 15.4 % |
| O3 | 2,306 | 13.1 % |
| SO2, CO | 3,829 | 0 % |

PM2.5 is a heating-season problem:

| Month | Mean PM2.5 (µg/m³) | Station-days above 15 µg/m³ | Mean temperature |
|---|---:|---:|---:|
| January | 35.6 | 82 % | -4.5 °C |
| February | 25.9 | 79 % | -2.0 °C |
| March | 23.7 | 80 % | 6.9 °C |
| April | 12.7 | 29 % | 8.4 °C |
| May | 10.2 | 10 % | 14.9 °C |
| June | 9.7 | 10 % | 19.7 °C |

And wind is what clears it. PM10 from January to March by the day's mean wind speed:

| Wind | Station-days | Mean PM10 (µg/m³) | Above 45 µg/m³ |
|---|---:|---:|---:|
| under 2 m/s | 587 | 53.5 | 53.3 % |
| 2 to 4 m/s | 1,518 | 37.4 | 27.7 % |
| 4 m/s and more | 469 | 23.5 | 7.2 % |

The worst day in the data is 20 January in Kraków: a daily mean of 212 µg/m³ of PM10 at
ul. Bujaka, at -10 °C and 0.8 m/s of wind.

## Found along the way

- The old GIOŚ paths (`/pjp-api/rest`) answer `410 Gone`. The current API is `/pjp-api/v1/rest`.
- The current-data endpoint only covers the last three days, so everything goes through the archive
  endpoint. It can take 10 to 20 seconds for a sensor it has not served recently, which is why
  sensors are fetched four at a time.
- Six sensors in the first two-day load returned daily values with codes ending in `-24g`: filters
  weighed by hand, published under the same pollutant as the hourly analysers. They are left out
  at load, and a test keeps them out.
- The first build on the full history stopped on three ozone results: -0.1, -0.2 and -0.1 µg/m³ at
  one Kraków station on 14 and 15 January. An analyser in clean air reads around zero; the lower
  bounds are now a little below it.
- Reloading the history reported 218 changed results on days where nothing had changed. For
  29 March, the day the clocks went forward, the archive has no result at 02:00 and two at 03:00
  for every sensor, although its timestamps are CET. The two shared a key and overwrote each
  other. The client now gives the first of them its hour back.
- A failed range test at first held back only the daily mart. dbt holds a model back when
  everything the failed test reads is upstream of it, and the hourly fact did not read the
  reference data. It does now.

## Layout

```
config/cities.yml          cities, weather points and tracked pollutants
src/airquality/            API clients, loader and the ingest command
sql/raw_schema.sql         the raw tables
dbt/                       sources, staging, marts, seed, generic and singular tests, unit tests
dags/                      the DAG, the alert callback, the rule for which day a run loads
docker/                    Airflow image, database init
analysis/                  queries on the marts
tests/                     Python tests, saved API responses, dbt and DAG tests
.github/workflows/ci.yml   CI
```

## Limits

- Weather is one point per city, not per station.
- Results are stored as GIOŚ publishes them. Recent results have not been through its yearly
  validation and may still be corrected; a run reloads only the two days before its own.
- The 8-hour mean is assigned to the day it ends on and needs six of its eight hours. The daily
  completeness rule is the usual 75 %. Neither follows the reporting rules to the letter.
- Airflow runs as a single container. A real deployment would separate the scheduler, the API
  server and the workers.
