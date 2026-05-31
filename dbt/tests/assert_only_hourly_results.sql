-- The hourly tables must hold hourly results only. Sensor codes end in the averaging
-- time: -1g for an hour, -24g for the daily samples weighed by hand.

select sensor_id, sensor_code, measured_at_cet
from {{ ref('stg_gios__measurements') }}
where sensor_code not like '%-1g'
