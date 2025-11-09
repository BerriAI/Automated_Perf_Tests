# LiteLLM Performance Regression Tests

## Overview

This repository contains automated Locust load tests for LiteLLM endpoints, allowing us to detect performance regressions. The currently targeted endpoints are:

- `chat/completions`
- `v1/responses`
- `embeddings`

A lightweight FastAPI service (`server.py`) orchestrates the runs. It validates a bearer token, loads the Locust scenarios, executes them in a background thread, and returns aggregated statistics in a single JSON payload.

Each scenario is configured through environment variables. See `docs/CONFIG.md` for the full matrix of options and defaults.

## Requirements

- Python 3.11+
- Poetry 1.6+ (`pipx install poetry` or see https://python-poetry.org/docs/#installation)

## Setup

Create an isolated virtual environment and install dependencies:

```
poetry install
```

Optionally activate the shell for interactive work:

```
poetry shell
```

## Environment Variables

Two variables must be present before triggering any test:

- `LOCUST_API_KEY`: forwarded as a bearer token by every Locust user. Missing this value causes the run to fail immediately and it must match the credential expected by LiteLLM gateway.
- `LOAD_TEST_BEARER_TOKEN`: secret required by the FastAPI server’s `/run-load-tests` endpoint. The value exported here must be identical to the bearer token you send in the request header.

Set both variables in the same environment where you launch the server or standalone scripts so that the orchestrator and Locust workers share the credentials.

Each load test exposes additional overrides (duration, spawn rate, host, etc.). These are optional and documented in `docs/CONFIG.md`.

## Running the FastAPI Orchestrator

1. Export the required environment variables:
   ```
   export LOCUST_API_KEY=your_api_key
   export LOAD_TEST_BEARER_TOKEN=your_server_secret
   ```
2. Start the API:
   ```
   poetry run uvicorn server:app --reload
   ```
3. Trigger a run with a POST request:
   ```
   curl -X POST http://localhost:8000/run-load-tests \
     -H "Authorization: Bearer ${LOAD_TEST_BEARER_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{
       "chat": {"duration_seconds": 120, "user_count": 5},
       "responses": {"user_count": 3},
       "embeddings": null
     }'
   ```

All `chat`, `responses`, and `embeddings` override objects are optional. Omitting a section (or setting it to `null`) falls back to the defaults listed in `docs/CONFIG.md`.

The server responds with per-scenario metrics including request counts, failure counts, latency percentiles, and LiteLLM overhead statistics.

## Running Scenarios Manually

Each script under `load_tests/` can be executed directly for ad-hoc testing:

```
poetry run python load_tests/chat-completions_load-test.py
```

The scripts honour the same environment variables as the server-driven runs and emit a JSON summary when complete.
