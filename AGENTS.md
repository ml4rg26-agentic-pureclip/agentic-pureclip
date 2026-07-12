# Repository Guidelines

## Project Structure & Module Organization

Core Python code uses a `src/` layout under `src/agentic_pureclip/`. Optimization logic lives in `loop/`, scoring in `scoring/`, Snakemake post-processing in `postprocess/`, shared pipeline utilities in `pipeline/`, and CLI scheduling in `run/`. Tests are in `tests/` and generally mirror these modules. Run and dataset YAML files belong in `config/`; operational utilities belong in `scripts/`. The monitoring application is split between `dashboard/api/` (FastAPI) and `dashboard/ui/` (React/TypeScript). Architecture notes and thesis sources live in `docs/`. Do not commit generated `data/`, `ref/`, or `results/` content.

## Build, Test, and Development Commands

- `uv sync`: create the Python environment and install the package editable.
- `uv run pytest -q`: run the complete pytest suite.
- `uv run pytest tests/test_report.py -q`: run one focused test module.
- `CONFIG_PATH=config/run_config.yaml MAX_ITER=2 uv run python -m agentic_pureclip.loop.graph`: run a short LLM optimization.
- `uv run agentic-pureclip-run --help`: inspect the supported batch-run CLI.
- `uv run uvicorn dashboard.api.main:app --port 8888 --reload`: start the dashboard API.
- `cd dashboard/ui && npm install && npm run dev`: start the UI locally.
- `cd dashboard/ui && npm run typecheck && npm run build`: validate and build the UI.

## Coding Style & Naming Conventions

Use four spaces, type hints, and `snake_case` for Python functions/modules; use `PascalCase` for classes. Keep configuration access centralized in `pipeline/configs.py` and prefer `pathlib.Path` for filesystem work. TypeScript uses two spaces, semicolons, `camelCase` variables, and `PascalCase` React components. No repository-wide formatter is configured, so match nearby code and keep imports grouped.

## Testing Guidelines

Pytest discovers `tests/test_*.py`; name tests `test_<behavior>`. Add unit coverage for config validation, scoring, scheduling, and failure paths near the changed behavior. Mark tests that call external services or full pipelines with `@pytest.mark.integration`. Standard tests should not require real credentials; use `DEEPSEEK_API_KEY=dummy` where necessary.

## Commit & Pull Request Guidelines

Recent commits use concise, imperative summaries, sometimes scoped (`docs:`, `dashboard:`), and often append the PR number. Keep each commit focused, for example `dashboard: validate run filters`. Pull requests should explain motivation and behavior, list verification commands, link relevant issues, and include screenshots for UI changes. Call out configuration, data, or compute requirements explicitly; never commit `.env`, API keys, BAM files, references, or generated results.
