-- Queries on the marts. The figures in the README come from these.

-- 1. How often is each pollutant above the WHO short-term guideline?
--    Counted over station-days with at least 18 measured hours.
select
    pollutant_code,
    count(*)                                                as station_days,
    count(*) filter (where is_complete_day)                 as complete_days,
    count(*) filter (where exceeds_who_guideline)           as days_above,
    round(100.0 * count(*) filter (where exceeds_who_guideline)
          / nullif(count(*) filter (where is_complete_day), 0), 1) as pct_above
from marts.mart_station_daily
group by pollutant_code
order by pct_above desc;


-- 2. PM2.5 through the year: monthly mean, share of station-days above the guideline, temperature.
select
    to_char(measured_on, 'YYYY-MM')                            as month,
    round(avg(daily_mean), 1)                                  as mean_pm25,
    round(100.0 * avg(exceeds_who_guideline::int), 0)          as pct_days_above,
    round(avg(avg_temperature_c), 1)                           as mean_temperature_c
from marts.mart_station_daily
where pollutant_code = 'PM2.5'
  and is_complete_day
group by 1
order by 1;


-- 3. Does wind clear the air? PM10 in the heating season by the day's mean wind speed.
select
    case
        when avg_wind_speed_ms < 2 then '1: under 2 m/s'
        when avg_wind_speed_ms < 4 then '2: 2 to 4 m/s'
        else '3: 4 m/s and more'
    end                                                        as wind,
    count(*)                                                   as station_days,
    round(avg(daily_mean), 1)                                  as mean_pm10,
    round(100.0 * avg(exceeds_who_guideline::int), 1)          as pct_days_above
from marts.mart_station_daily
where pollutant_code = 'PM10'
  and is_complete_day
  and measured_on < date '2026-04-01'
group by 1
order by 1;


-- 4. PM2.5 by city.
select
    city,
    count(distinct station_id)                                 as stations,
    round(avg(daily_mean), 1)                                  as mean_pm25,
    round(100.0 * avg(exceeds_who_guideline::int), 0)          as pct_days_above
from marts.mart_station_daily
where pollutant_code = 'PM2.5'
  and is_complete_day
group by city
order by mean_pm25 desc;


-- 5. The ten worst station-days for PM10, with the weather of the day.
select
    measured_on,
    station_name,
    daily_mean,
    daily_max,
    hours_measured,
    avg_temperature_c,
    avg_wind_speed_ms
from marts.mart_station_daily
where pollutant_code = 'PM10'
  and is_complete_day
order by daily_mean desc
limit 10;


-- 6. Which stations report the fewest hours? Share of the hours in the period that have a result.
select
    s.station_name,
    f.pollutant_code,
    count(*)                                                   as hours_measured,
    round(100.0 * count(*)
          / (extract(epoch from max(f.measured_at_cet) - min(f.measured_at_cet)) / 3600 + 1), 1) as pct_of_hours
from marts.fct_measurement_hourly as f
join marts.dim_station as s using (station_id)
group by s.station_name, f.pollutant_code
order by pct_of_hours
limit 10;


-- 7. Hour-of-day profile of NO2 at one station, working days against weekends (local clock is CET here).
select
    extract(hour from f.measured_at_cet)::int                  as hour_cet,
    round(avg(f.value) filter (where extract(isodow from f.measured_at_cet) < 6)::numeric, 1)  as working_days,
    round(avg(f.value) filter (where extract(isodow from f.measured_at_cet) >= 6)::numeric, 1) as weekends
from marts.fct_measurement_hourly as f
join marts.dim_station as s using (station_id)
where f.pollutant_code = 'NO2'
  and s.station_code = 'MzWarAlNiepo'
group by 1
order by 1;
