import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, status
from helpers import LoadTestRequest, SUPPORTED_TESTS, TestOverride, get_bearer_token


app = FastAPI(title="Locust Load Test Runner", version="1.0.0")


def _require_valid_bearer_token(authorization: Optional[str]) -> None:
    expected_token = os.environ.get("LOAD_TEST_BEARER_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server is not configured with LOAD_TEST_BEARER_TOKEN.",
        )

    supplied_token = get_bearer_token(authorization)
    if supplied_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.post("/run-load-tests")
async def run_load_tests(
    request: Optional[LoadTestRequest] = None, authorization: Optional[str] = Header(default=None)
):
    _require_valid_bearer_token(authorization)

    payload = request or LoadTestRequest()

    results = {}
    for test_name, test_runner in SUPPORTED_TESTS.items():
        override = getattr(payload, test_name, None)
        try:
            results[test_name] = test_runner(override)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to execute {test_name} load test: {exc}",
            ) from exc

    return {"results": results}


@app.post("/run-load-tests/{test_name}")
async def run_single_load_test(
    test_name: str,
    request: Optional[TestOverride] = None,
    authorization: Optional[str] = Header(default=None),
):
    _require_valid_bearer_token(authorization)

    test_runner = SUPPORTED_TESTS.get(test_name)
    if not test_runner:
        supported_tests = ", ".join(sorted(SUPPORTED_TESTS.keys()))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unsupported load test '{test_name}'. Supported tests: {supported_tests}",
        )

    try:
        result = test_runner(request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute {test_name} load test: {exc}",
        ) from exc

    return {"test": test_name, "result": result}


__all__ = ["app"]

