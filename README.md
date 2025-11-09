# LiteLLM Load Tests

This repository provides **FastAPI endpoints and Locust scenarios** for automated load testing of LiteLLM. These tests help track latency regressions across key endpoints:

* `chat/completions`
* `v1/responses`
* `embeddings`

Use these tests to **detect performance regressions or validate performance improvements**. See `docs/CONFIG.md` for all available overrides and default settings.

## Requirements

* Python 3.11+
* Poetry 1.6+

```
poetry install
poetry shell  # optional
```

## Required Environment

Set these variables in the shell before launching the server or scripts:

```
export LOCUST_API_KEY=...
export LOAD_TEST_BEARER_TOKEN=...
```

Other parameters (test duration, spawn rate, host, etc.) are optional. Refer to `docs/CONFIG.md` for details.

## API Usage

Start the orchestrator:

```
poetry run uvicorn server:app --reload
```

Run all tests:

```
curl -X POST http://localhost:8000/run-load-tests \
  -H "Authorization: Bearer ${LOAD_TEST_BEARER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"chat": {"duration_seconds": 120}}'
```

Run a single test with custom overrides:

```
curl -X POST http://localhost:8000/run-load-tests/chat \
  -H "Authorization: Bearer ${LOAD_TEST_BEARER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"user_count": 5, "spawn_rate": 2}'
```

Responses include **request totals, failure counts, latency percentiles, and LiteLLM-specific overhead statistics**, making it easy to analyze performance trends.

## Direct Locust Runs

Each script in `load_tests/` can also be invoked directly without the API:

```
poetry run python load_tests/chat-completions_load-test.py
```

Output metrics match those returned by the FastAPI orchestrator, allowing flexible testing workflows.