from __future__ import annotations
from functools import wraps
from typing import Callable, Any

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("repo_intelligence")
except ImportError:  # pragma: no cover
    _tracer = None


def instrument(name: str | None = None) -> Callable:
    """Decorator that optionally creates OpenTelemetry spans for functions.

    If OpenTelemetry is not installed or not configured, the decorator is a no-op.
    """

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__qualname__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _tracer is None:
                return func(*args, **kwargs)
            with _tracer.start_as_current_span(span_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def get_tracer():
    return _tracer
