select
    station_id,
    code       as station_code,
    name       as station_name,
    city,
    voivodeship,
    street,
    latitude,
    longitude,
    loaded_at
from {{ source('raw', 'gios_station') }}
