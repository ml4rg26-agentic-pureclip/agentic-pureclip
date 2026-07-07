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

# Install uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install the project (src/agentic_pureclip + fastapi/uvicorn) into the image.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# The API package (not part of the wheel — run from source).
COPY dashboard/api ./dashboard/api

EXPOSE 8888
CMD ["uv", "run", "uvicorn", "dashboard.api.main:app", "--host", "0.0.0.0", "--port", "8888"]
