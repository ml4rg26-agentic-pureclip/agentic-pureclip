# FastAPI data provider for the dashboard. Build from the repository root so the
# core package (src/agentic_pureclip) and the collectors are both in context:
#
#   docker build -f dashboard/api/Dockerfile -t agentic-pureclip-api .
#   docker run -p 8888:8888 -v "$PWD/results:/app/results" -v "$PWD/config:/app/config" agentic-pureclip-api
#
# The collectors read results/ and config/ relative to the working directory, so
# mount those (and the running pipeline's process list is only meaningful when the
# API runs on the same host as the optimisation jobs).
FROM python:3.10-slim

WORKDIR /app

# procps provides `ps`, which the collectors scan to detect running pipeline jobs
# (get_processes / _run_active). Combined with `pid: host` in compose, the scan
# then sees the host's optimisation processes rather than just the container's.
RUN apt-get update && apt-get install -y --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install the project (src/agentic_pureclip + fastapi/uvicorn) into the image.
# build-essential is needed to compile sdist-only deps (e.g. datrie, via snakemake);
# it is purged again in the same layer so it never reaches the runtime image.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && uv sync --frozen --no-dev \
    && apt-get purge -y build-essential && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# The API package (not part of the wheel — run from source).
COPY dashboard/api ./dashboard/api

EXPOSE 8888
CMD ["uv", "run", "uvicorn", "dashboard.api.main:app", "--host", "0.0.0.0", "--port", "8888"]
