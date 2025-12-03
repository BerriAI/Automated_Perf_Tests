import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, status
from helpers import LoadTestRequest, SUPPORTED_TESTS, TestOverride, get_bearer_token


app = FastAPI(title="Locust Load Test Runner", version="1.0.0")


# Predefined intensity level configurations
INTENSITY_LEVELS = {
    ## make it 5 minutes, 1000 users 500 ramp up
    "light": TestOverride(
        duration_seconds=300,  # 5 minutes
        user_count=1000,
        spawn_rate=500.0,
    ),
    ## make it 10 minutes, 1000 users 500 ramp up
    "normal": TestOverride(
        duration_seconds=600,  # 10 minutes
        user_count=1000,
        spawn_rate=500.0,
    ),
    ## make it 20 minutes, 1000 users 500 ramp up
    "medium": TestOverride(
        duration_seconds=1200,  # 20 minutes
        user_count=1000,
        spawn_rate=500.0,
    ),
    ## make it 30 minutes, 1000 users 500 ramp up
    "intense": TestOverride(
        duration_seconds=1800,  # 30 minutes
        user_count=1000,
        spawn_rate=500.0,   
    ),
    ## make it 10 hrs, 1000 users 500 ramp up
    "OOM": TestOverride(
        duration_seconds=36000,  # 10 hours
        user_count=1000,
        spawn_rate=500.0,
    ),
}


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


@app.post("/run-load-tests/{test_name}/{intensity_level}")
async def run_load_test_with_intensity(
    test_name: str,
    intensity_level: str,
    request: Optional[TestOverride] = None,
    authorization: Optional[str] = Header(default=None),
):
    _require_valid_bearer_token(authorization)

    # Validate intensity level
    if intensity_level not in INTENSITY_LEVELS:
        supported_levels = ", ".join(sorted(INTENSITY_LEVELS.keys()))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported intensity level '{intensity_level}'. Supported levels: {supported_levels}",
        )

    # Validate test name
    test_runner = SUPPORTED_TESTS.get(test_name)
    if not test_runner:
        supported_tests = ", ".join(sorted(SUPPORTED_TESTS.keys()))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unsupported load test '{test_name}'. Supported tests: {supported_tests}",
        )

    # Start with predefined intensity configuration
    intensity_config = INTENSITY_LEVELS[intensity_level]
    
    # Merge with optional request overrides (request takes precedence)
    final_override = TestOverride(
        duration_seconds=request.duration_seconds if request and request.duration_seconds is not None else intensity_config.duration_seconds,
        user_count=request.user_count if request and request.user_count is not None else intensity_config.user_count,
        spawn_rate=request.spawn_rate if request and request.spawn_rate is not None else intensity_config.spawn_rate,
        host=request.host if request and request.host is not None else intensity_config.host,
    )

    try:
        result = test_runner(final_override)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute {test_name} load test: {exc}",
        ) from exc

    return {
        "test": test_name,
        "intensity_level": intensity_level,
        "configuration": {
            "duration_seconds": final_override.duration_seconds,
            "user_count": final_override.user_count,
            "spawn_rate": final_override.spawn_rate,
            "host": final_override.host,
        },
        "result": result,
    }


__all__ = ["app"]

