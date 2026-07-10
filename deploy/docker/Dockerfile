FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

ARG RELEASE_ID=development
ARG SOURCE_COMMIT=unknown
ARG RW_TASK_SNAPSHOT=unknown
ARG APP_UID=1000
ARG APP_GID=1000

LABEL org.opencontainers.image.title="TaskGenerator" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      cloud.huago.taskgenerator.release="${RELEASE_ID}" \
      cloud.huago.taskgenerator.managed="true"

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=0 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    TASKGEN_OUTPUT_ROOT=/data/runs \
    TASKGEN_RW_TASK_ROOT=/opt/rw-task \
    TASKGEN_ENV_PATH=/run/secrets/provider_env \
    TASKGEN_DEEPSEEK_KEY_PATH=/run/secrets/deepseek_api_key \
    TASKGEN_RELEASE_ID=${RELEASE_ID} \
    TASKGEN_SOURCE_COMMIT=${SOURCE_COMMIT} \
    TASKGEN_RW_TASK_SNAPSHOT=${RW_TASK_SNAPSHOT} \
    TASKGEN_EXECUTION_PLATFORM=container \
    TASKGEN_CPU_LIMIT=1.5 \
    TASKGEN_MEMORY_LIMIT=2.5g

RUN groupadd --gid "${APP_GID}" taskgenerator \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home taskgenerator

COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --upgrade pip==26.1.1 setuptools==80.10.2 wheel==0.46.3 \
    && python -m pip install --no-cache-dir -r /tmp/requirements.lock

COPY rw-task /opt/rw-task
RUN python -m pip install --no-cache-dir --no-deps /opt/rw-task

COPY taskgenerator /opt/taskgenerator
RUN python -m pip install --no-cache-dir --no-deps /opt/taskgenerator \
    && mkdir -p /data/runs /data/input /run/secrets \
    && chown -R taskgenerator:taskgenerator /data /run/secrets

WORKDIR /opt/taskgenerator
USER taskgenerator
ENTRYPOINT ["python", "Test/run_v3_end_to_end_pipeline.py"]
CMD ["--help"]
