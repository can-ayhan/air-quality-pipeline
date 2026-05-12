-- Raw layer: what the two APIs returned, one table per endpoint.
-- Primary keys make every load repeatable: running the same day twice
-- updates the rows instead of adding them again.

create schema if not exists raw;

create table if not exists raw.gios_station (
    station_id   integer primary key,
    code         text not null,
    name         text not null,
    city         text not null,
    voivodeship  text,
    street       text,
    latitude     double precision,
    longitude    double precision,
    loaded_at    timestamptz not null default now()
);

create table if not exists raw.gios_sensor (
    sensor_id       integer primary key,
    station_id      integer not null,
    pollutant_code  text not null,
    pollutant_name  text,
    loaded_at       timestamptz not null default now()
);

create table if not exists raw.gios_measurement (
    sensor_id        integer   not null,
    sensor_code      text      not null,
    measured_at_cet  timestamp not null,     -- as published: CET (UTC+1) all year, no daylight saving
    value            double precision,       -- NULL: the hour was reported without a valid result
    loaded_at        timestamptz not null default now(),
    primary key (sensor_id, measured_at_cet)
);

create table if not exists raw.openmeteo_hourly (
    city                   text      not null,
    time_utc               timestamp not null,
    temperature_c          double precision,
    relative_humidity_pct  double precision,
    wind_speed_ms          double precision,
    wind_direction_deg     double precision,
    precipitation_mm       double precision,
    surface_pressure_hpa   double precision,
    loaded_at              timestamptz not null default now(),
    primary key (city, time_utc)
);
