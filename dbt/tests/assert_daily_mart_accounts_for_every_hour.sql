-- The daily mart is an aggregate of the hourly fact: the hours it counts must add up
-- to the rows of the fact. A join that drops or doubles rows shows up here.

with fact as (

    select count(*) as hours from {{ ref('fct_measurement_hourly') }}

),

mart as (

    select coalesce(sum(hours_measured), 0) as hours from {{ ref('mart_station_daily') }}

)

select fact.hours as hours_in_fact, mart.hours as hours_in_mart
from fact
cross join mart
where fact.hours <> mart.hours
