-- Runs once, when the PostgreSQL volume is first created.
-- Airflow keeps its own state in a separate database on the same server.
create role airflow login password 'airflow';
create database airflow owner airflow;
