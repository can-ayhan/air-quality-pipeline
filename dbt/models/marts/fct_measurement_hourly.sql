{{
    config(
        materialized='incremental',
        unique_key=['sensor_id', 'measured_at_utc'],
        on_schema_change='fail',
        indexes=[
            {'columns': ['sensor_id', 'measured_at_utc'], 'unique': True},
            {'columns': ['station_id', 'pollutant_code', 'measured_on']}
        ]
    )
}}

-- One row per sensor and hour with a valid result.
--
-- Incremental on loaded_at, not on the measurement time: a backfill or a reload of an
-- old day writes rows with old timestamps and a new loaded_at. They come through here
-- again and replace themselves on the key.

with measurements as (

    select * from {{ ref('stg_gios__measurements') }}
    where value is not null
    {% if is_incremental() %}
      and loaded_at > (select coalesce(max(loaded_at), '-infinity') from {{ this }})
    {% endif %}

),

sensors as (

    select * from {{ ref('stg_gios__sensors') }}

),

-- The unit comes from the reference data (CO is in mg/m3, the rest in µg/m3).
-- Reading it here also puts this model downstream of everything the plausibility
-- test reads, which is what makes dbt hold this model back when that test fails.
pollutants as (

    select pollutant_code, unit from {{ ref('pollutant_limits') }}

)

select
    measurements.sensor_id,
    sensors.station_id,
    sensors.pollutant_code,
    measurements.measured_at_utc,
    measurements.measured_at_cet,
    measurements.measured_on,
    measurements.value,
    pollutants.unit,
    measurements.loaded_at
from measurements
join sensors using (sensor_id)
join pollutants using (pollutant_code)
