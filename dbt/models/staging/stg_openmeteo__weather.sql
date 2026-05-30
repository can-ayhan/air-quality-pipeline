select
    city,
    time_utc,
    temperature_c,
    relative_humidity_pct,
    wind_speed_ms,
    wind_direction_deg,
    precipitation_mm,
    surface_pressure_hpa,
    loaded_at
from {{ source('raw', 'openmeteo_hourly') }}
