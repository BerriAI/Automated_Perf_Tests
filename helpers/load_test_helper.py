from __future__ import annotations

import importlib.util
import os
import statistics
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from fastapi import HTTPException, status
import gevent
from locust import events as locust_events
from locust.env import Environment
from locust.user import User
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
LOAD_TESTS_DIR = BASE_DIR / "load_tests"


def load_module(module_name: str, file_path: Path):
    """Dynamically load a Python module from an arbitrary file path."""
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


@lru_cache(maxsize=None)
def get_chat_module():
    return load_module(
        "load_tests.chat_completions_load_test",
        LOAD_TESTS_DIR / "chat-completions_load-test.py",
    )


@lru_cache(maxsize=None)
def get_responses_module():
    return load_module(
        "load_tests.responses_load_test",
        LOAD_TESTS_DIR / "responses_load-test.py",
    )


@lru_cache(maxsize=None)
def get_embeddings_module():
    return load_module(
        "load_tests.embeddings_load_test",
        LOAD_TESTS_DIR / "embeddings_load-test.py",
    )


class TestOverride(BaseModel):
    duration_seconds: Optional[int] = None
    user_count: Optional[int] = None
    spawn_rate: Optional[float] = None
    host: Optional[str] = None


class LoadTestRequest(BaseModel):
    chat: Optional[TestOverride] = None
    responses: Optional[TestOverride] = None
    embeddings: Optional[TestOverride] = None


DEFAULT_DURATION_CONFIG = {
    "chat": ("LOCUST_CHAT_DURATION_SECONDS", "60"),
    "responses": ("LOCUST_RESPONSES_DURATION_SECONDS", "60"),
    "embeddings": ("LOCUST_EMBEDDINGS_DURATION_SECONDS", "60"),
}


def get_bearer_token(auth_header: Optional[str]) -> str:
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, param = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not param:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return param.strip()


def resolve_override(
    override: Optional[Any], field: str, default_factory: Callable[[], str]
):
    if override is None:
        return default_factory()

    value = getattr(override, field, None)
    if value is None:
        return default_factory()
    return value


def resolve_host(override: Optional[TestOverride], env_var: str) -> Optional[str]:
    if override and override.host:
        return override.host

    global_host = os.environ.get("LOCUST_HOST")
    if global_host:
        return global_host

    return os.environ.get(env_var)


def run_chat_test(override: Optional[TestOverride]) -> Dict:
    chat_module = get_chat_module()

    duration_seconds = int(
        resolve_override(
            override,
            "duration_seconds",
            lambda: os.environ.get("LOCUST_CHAT_DURATION_SECONDS", "60"),
        )
    )
    user_count = int(
        resolve_override(
            override,
            "user_count",
            lambda: os.environ.get("LOCUST_CHAT_USER_COUNT", "1"),
        )
    )
    spawn_rate = float(
        resolve_override(
            override,
            "spawn_rate",
            lambda: os.environ.get("LOCUST_CHAT_SPAWN_RATE", "1.0"),
        )
    )
    host = resolve_host(override, "LOCUST_CHAT_HOST")

    return chat_module.run_locust_load_test(
        duration_seconds=duration_seconds,
        user_count=user_count,
        spawn_rate=spawn_rate,
        host=host,
        user_classes=[chat_module.MyUser],
        events=chat_module.events,
        overhead_durations=chat_module.overhead_durations,
    )


def run_responses_test(override: Optional[TestOverride]) -> Dict:
    responses_module = get_responses_module()

    duration_seconds = int(
        resolve_override(
            override,
            "duration_seconds",
            lambda: os.environ.get("LOCUST_RESPONSES_DURATION_SECONDS", "60"),
        )
    )
    user_count = int(
        resolve_override(
            override,
            "user_count",
            lambda: os.environ.get("LOCUST_RESPONSES_USER_COUNT", "1"),
        )
    )
    spawn_rate = float(
        resolve_override(
            override,
            "spawn_rate",
            lambda: os.environ.get("LOCUST_RESPONSES_SPAWN_RATE", "1.0"),
        )
    )
    host = resolve_host(override, "LOCUST_RESPONSES_HOST")

    return responses_module.run_locust_load_test(
        duration_seconds=duration_seconds,
        user_count=user_count,
        spawn_rate=spawn_rate,
        host=host,
        user_classes=[responses_module.ResponsesUser],
        events=responses_module.events,
        overhead_durations=responses_module.overhead_durations,
    )


def run_embeddings_test(override: Optional[TestOverride]) -> Dict:
    embeddings_module = get_embeddings_module()

    duration_seconds = int(
        resolve_override(
            override,
            "duration_seconds",
            lambda: os.environ.get("LOCUST_EMBEDDINGS_DURATION_SECONDS", "60"),
        )
    )
    user_count = int(
        resolve_override(
            override,
            "user_count",
            lambda: os.environ.get("LOCUST_EMBEDDINGS_USER_COUNT", "1"),
        )
    )
    spawn_rate = float(
        resolve_override(
            override,
            "spawn_rate",
            lambda: os.environ.get("LOCUST_EMBEDDINGS_SPAWN_RATE", "1.0"),
        )
    )
    host = resolve_host(override, "LOCUST_EMBEDDINGS_HOST")

    return embeddings_module.run_locust_load_test(
        duration_seconds=duration_seconds,
        user_count=user_count,
        spawn_rate=spawn_rate,
        host=host,
        user_classes=[embeddings_module.EmbeddingsUser],
        events=embeddings_module.events,
        overhead_durations=embeddings_module.overhead_durations,
    )


SUPPORTED_TESTS: Dict[str, Callable[[Optional[TestOverride]], Dict]] = {
    "chat": run_chat_test,
    "responses": run_responses_test,
    "embeddings": run_embeddings_test,
}


def execute_all_tests(payload: LoadTestRequest) -> Dict[str, Dict]:
    results: Dict[str, Dict] = {}
    for test_name, test_runner in SUPPORTED_TESTS.items():
        override = getattr(payload, test_name, None)
        results[test_name] = test_runner(override)
    return results


def _resolve_duration_seconds(override: Optional[TestOverride], env_var: str, default_value: str) -> int:
    value = resolve_override(
        override,
        "duration_seconds",
        lambda: os.environ.get(env_var, default_value),
    )
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid duration_seconds provided for {env_var}: {value}") from exc


def calculate_expected_run_duration(payload: LoadTestRequest) -> int:
    payload = payload or LoadTestRequest()

    durations = [
        _resolve_duration_seconds(payload.chat, *DEFAULT_DURATION_CONFIG["chat"]),
        _resolve_duration_seconds(payload.responses, *DEFAULT_DURATION_CONFIG["responses"]),
        _resolve_duration_seconds(payload.embeddings, *DEFAULT_DURATION_CONFIG["embeddings"]),
    ]
    return sum(max(duration, 0) for duration in durations)


def run_locust_load_test(
    duration_seconds: int,
    user_count: int = 1,
    spawn_rate: float = 1.0,
    host: Optional[str] = None,
    *,
    user_classes: Sequence[type[User]],
    events=locust_events,
    overhead_durations: list[float] | None = None,
) -> dict:
    """
    Programmatically execute the Locust scenario for a fixed duration and collect summary stats.

    Args:
        duration_seconds: How long to run the load test before stopping.
        user_count: Target number of concurrent simulated users.
        spawn_rate: Rate at which users are spawned (users per second).
        host: Optional override for the base host. Defaults to Locust's configured host.
        user_classes: Locust user classes to include in the test.
        events: Locust events dispatcher.
        overhead_durations: Mutable sequence used to aggregate LiteLLM overhead durations.

    Returns:
        A dictionary containing aggregate request metrics, errors, and LiteLLM overhead stats.
    """
    if not user_classes:
        raise ValueError("At least one user class must be provided.")

    if not os.environ.get("LOCUST_API_KEY"):
        raise RuntimeError("LOCUST_API_KEY environment variable is required.")

    if overhead_durations is None:
        overhead_durations = []

    overhead_durations.clear()

    env = Environment(user_classes=list(user_classes), events=events)

    if host:
        env.host = host
        for user_class in env.user_classes:
            user_class.host = host

    env.create_local_runner()
    env.runner.start(user_count, spawn_rate=spawn_rate)

    # Stop after the requested duration
    gevent.spawn_later(duration_seconds, env.runner.quit)
    env.runner.greenlet.join()

    total_stats = env.stats.total

    errors = []
    for error in env.stats.errors:
        error_entry: dict[str, str | int | None] = {
            "method": getattr(error, "method", None),
            "name": getattr(error, "name", None),
            "occurrences": getattr(error, "occurrences", getattr(error, "occurences", 0)),
            "error": str(getattr(error, "error", error)),
        }
        errors.append(error_entry)

    overhead_summary: dict[str, float | int] = {"count": len(overhead_durations)}
    if overhead_durations:
        overhead_summary.update(
            {
                "min_ms": min(overhead_durations),
                "max_ms": max(overhead_durations),
                "avg_ms": statistics.fmean(overhead_durations),
                "median_ms": statistics.median(overhead_durations),
            }
        )

    result = {
        "duration_seconds": duration_seconds,
        "user_count": user_count,
        "spawn_rate": spawn_rate,
        "requests": total_stats.num_requests,
        "failures": total_stats.num_failures,
        "avg_response_time_ms": total_stats.avg_response_time,
        "median_response_time_ms": total_stats.get_response_time_percentile(0.5),
        "p95_response_time_ms": total_stats.get_response_time_percentile(0.95),
        "max_response_time_ms": total_stats.max_response_time,
        "requests_per_second": total_stats.total_rps,
        "failures_per_second": total_stats.total_fail_per_sec,
        "errors": errors,
        "overhead_summary": overhead_summary,
    }

    return result


__all__ = [
    "load_module",
    "LoadTestRequest",
    "TestOverride",
    "get_bearer_token",
    "calculate_expected_run_duration",
    "resolve_override",
    "resolve_host",
    "run_chat_test",
    "run_responses_test",
    "run_embeddings_test",
    "SUPPORTED_TESTS",
    "execute_all_tests",
    "run_locust_load_test",
    "get_chat_module",
    "get_responses_module",
    "get_embeddings_module",
]


