FROM apache/airflow:3.2.1-python3.12

# The pipeline (ingest package and dbt) lives in its own virtualenv. Airflow only
# starts commands in it, so their dependencies never have to agree with Airflow's.
ENV PIPELINE_HOME=/opt/pipeline \
    PIPELINE_VENV=/opt/pipeline-venv

USER root
RUN mkdir -p ${PIPELINE_HOME} ${PIPELINE_VENV} \
    && chown -R airflow:0 ${PIPELINE_HOME} ${PIPELINE_VENV}
USER airflow

RUN /usr/python/bin/python -m venv ${PIPELINE_VENV}

# dependencies first, so that editing a model or a DAG does not reinstall them
COPY --chown=airflow:0 pyproject.toml ${PIPELINE_HOME}/
COPY --chown=airflow:0 src ${PIPELINE_HOME}/src
RUN ${PIPELINE_VENV}/bin/pip install --no-cache-dir -e "${PIPELINE_HOME}[dbt]"

COPY --chown=airflow:0 config ${PIPELINE_HOME}/config
COPY --chown=airflow:0 sql ${PIPELINE_HOME}/sql
COPY --chown=airflow:0 dbt ${PIPELINE_HOME}/dbt
COPY --chown=airflow:0 dags ${AIRFLOW_HOME}/dags
