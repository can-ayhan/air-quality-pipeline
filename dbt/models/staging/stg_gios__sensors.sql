select
    sensor_id,
    station_id,
    pollutant_code,
    pollutant_name as pollutant_name_pl,
    loaded_at
from {{ source('raw', 'gios_sensor') }}
