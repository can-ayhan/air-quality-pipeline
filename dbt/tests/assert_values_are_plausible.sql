-- A result outside the plausible bounds of its pollutant is a unit or parsing error,
-- not pollution. The case this is here for: GIOS publishes CO in mg/m3 in the archive
-- endpoint and in µg/m3 in the current-data endpoint, a factor of 1000.

select
    m.sensor_id,
    s.pollutant_code,
    m.measured_at_cet,
    m.value,
    p.plausible_min,
    p.plausible_max
from {{ ref('stg_gios__measurements') }} as m
join {{ ref('stg_gios__sensors') }} as s using (sensor_id)
join {{ ref('pollutant_limits') }} as p using (pollutant_code)
where m.value < p.plausible_min
   or m.value > p.plausible_max
