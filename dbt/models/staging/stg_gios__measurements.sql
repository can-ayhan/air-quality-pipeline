-- GIOS publishes hourly results in CET (UTC+1) all year, without daylight saving.
-- Both clocks are kept: UTC to join the weather, CET because the day a result
-- belongs to is the CET day.

select
    sensor_id,
    sensor_code,
    measured_at_cet,
    measured_at_cet - interval '1 hour' as measured_at_utc,
    measured_at_cet::date               as measured_on,
    value,
    loaded_at
from {{ source('raw', 'gios_measurement') }}
