-- One row per station, pollutant and day: the figures a station is judged by,
-- next to the weather of that day in its city.

with hourly as (

    select * from {{ ref('fct_measurement_hourly') }}

),

rolling as (

    -- mean of the eight hours ending with each hour
    select
        sensor_id,
        measured_at_cet,
        avg(value)   over eight_hours as mean_8h,
        count(value) over eight_hours as hours_in_8h
    from hourly
    window eight_hours as (
        partition by sensor_id
        order by measured_at_cet
        range between interval '7 hours' preceding and current row
    )

),

daily as (

    select
        hourly.station_id,
        hourly.pollutant_code,
        hourly.measured_on,
        count(*)                                                         as hours_measured,
        round(avg(hourly.value)::numeric, 2)                             as daily_mean,
        round(max(hourly.value)::numeric, 2)                             as daily_max,
        -- an 8-hour mean counts with at least six of its hours
        round(max(rolling.mean_8h) filter (where rolling.hours_in_8h >= 6)::numeric, 2) as max_8h_mean
    from hourly
    join rolling using (sensor_id, measured_at_cet)
    group by 1, 2, 3

),

weather as (

    select
        city,
        observed_on,
        round(avg(temperature_c)::numeric, 1)         as avg_temperature_c,
        round(avg(relative_humidity_pct)::numeric, 0) as avg_relative_humidity_pct,
        round(avg(wind_speed_ms)::numeric, 1)         as avg_wind_speed_ms,
        round(sum(precipitation_mm)::numeric, 1)      as total_precipitation_mm
    from {{ ref('fct_weather_hourly') }}
    group by 1, 2

),

stations as (

    select * from {{ ref('dim_station') }}

),

pollutants as (

    select * from {{ ref('pollutant_limits') }}

)

select
    daily.station_id,
    stations.station_name,
    stations.city,
    daily.pollutant_code,
    pollutants.unit,
    daily.measured_on,
    daily.hours_measured,
    -- the usual rule for a valid daily value: three quarters of the hours
    daily.hours_measured >= 18 as is_complete_day,
    daily.daily_mean,
    daily.daily_max,
    daily.max_8h_mean,
    pollutants.who_guideline,
    case
        when daily.hours_measured < 18 then null
        when pollutants.who_basis = 'daily_mean' then daily.daily_mean > pollutants.who_guideline
        when pollutants.who_basis = 'max_8h_mean' then daily.max_8h_mean > pollutants.who_guideline
    end as exceeds_who_guideline,
    weather.avg_temperature_c,
    weather.avg_relative_humidity_pct,
    weather.avg_wind_speed_ms,
    weather.total_precipitation_mm
from daily
join stations using (station_id)
join pollutants using (pollutant_code)
left join weather
    on weather.city = stations.city
    and weather.observed_on = daily.measured_on
