-- One row per city and hour. observed_on is the CET date, the same day
-- definition as the measurements, so the two can be joined by day.

select
    city,
    time_utc,
    time_utc + interval '1 hour'           as time_cet,
    (time_utc + interval '1 hour')::date   as observed_on,
    temperature_c,
    relative_humidity_pct,
    wind_speed_ms,
    wind_direction_deg,
    precipitation_mm,
    surface_pressure_hpa
from {{ ref('stg_openmeteo__weather') }}
