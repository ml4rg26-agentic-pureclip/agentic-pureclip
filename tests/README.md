# Tests Module

This directory contains the automated test suite for the Agentic PureCLIP project, utilizing the `pytest` framework. 

## Files

- **`test_agent.py`**: Contains tests for the LangGraph state machine.
  - `test_convergence_plateau`: Tests if the agent halts execution when the objective score stops improving.
  - `test_hard_cap_always_up`: Tests if the agent halts execution when the maximum number of iterations is reached.
  - `test_real_gemini_api`: An integration test that uses the Google Gemini API to run a 2-iteration loop. This test requires a valid API key in the `.env` file.
- **`test_workflow.py`**: Contains tests for the Snakemake workflow.
  - `test_snakemake_dry_run`: Performs a Snakemake dry run to verify the `Snakefile` syntax and graph structure without executing bioinformatics tools.

## Usage

To run the standard test suite:
```bash
pytest
```

To run a specific test file:
```bash
pytest tests/test_agent.py
```

To run the real Gemini API integration test:
```bash
pytest tests/test_agent.py -k test_real_gemini_api -s
```
