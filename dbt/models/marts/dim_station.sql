with stations as (

    select * from {{ ref('stg_gios__stations') }}

),

sensors as (

    select
        station_id,
        count(*)                                                         as sensors,
        string_agg(distinct pollutant_code, ', ' order by pollutant_code) as pollutants
    from {{ ref('stg_gios__sensors') }}
    group by station_id

)

select
    stations.station_id,
    stations.station_code,
    stations.station_name,
    stations.city,
    stations.voivodeship,
    stations.street,
    stations.latitude,
    stations.longitude,
    coalesce(sensors.sensors, 0) as sensors,
    sensors.pollutants
from stations
left join sensors using (station_id)
