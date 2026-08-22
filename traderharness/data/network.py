"""Shared request pacing, retry and circuit-breaker primitives for free data APIs.

The goal is cooperative use of upstream services: every provider owns an
explicit request budget, 429 responses are obeyed, and access-denied responses
open a circuit instead of causing an aggressive retry storm.
"""

from __future__ import annotations

import email.utils
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


class ProviderBlockedError(RuntimeError):
    """The upstream rejected access and the local circuit breaker opened."""


class ProviderCircuitOpenError(RuntimeError):
    """A request was prevented because the provider cooldown is still active."""


@dataclass(frozen=True)
class RequestPolicy:
    max_attempts: int = 4
    base_backoff: float = 1.0
    max_backoff: float = 60.0
    jitter: float = 0.2
    forbidden_cooldown: float = 300.0
    max_retry_after: float = 300.0
    retry_statuses: tuple[int, ...] = (408, 425, 429, 500, 502, 503, 504)


class AdaptiveRequestGate:
    """Thread-safe minimum-interval limiter with a shared cooldown circuit."""

    def __init__(
        self,
        *,
        min_interval: float,
        sleeper: Callable[[float], Any] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be non-negative")
        self.min_interval = float(min_interval)
        self._sleep = sleeper
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._next_request_at = 0.0
        self.blocked_until = 0.0
        self.stats = {
            "requests": 0,
            "retries": 0,
            "rate_limited": 0,
            "blocked": 0,
            "server_errors": 0,
            "network_errors": 0,
        }

    def acquire(self) -> None:
        with self._lock:
            now = self._monotonic()
            if self.blocked_until > now:
                remaining = self.blocked_until - now
                raise ProviderCircuitOpenError(
                    f"provider circuit is open for another {remaining:.1f}s"
                )
            delay = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + self.min_interval
        if delay:
            self._sleep(delay)

    def defer(self, seconds: float, *, block: bool = False) -> None:
        delay = max(0.0, float(seconds))
        with self._lock:
            now = self._monotonic()
            self._next_request_at = max(self._next_request_at, now + delay)
            if block:
                self.blocked_until = max(self.blocked_until, now + delay)


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            retry_at = email.utils.parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _backoff(policy: RequestPolicy, attempt: int) -> float:
    base = min(policy.max_backoff, policy.base_backoff * (2 ** max(0, attempt - 1)))
    if policy.jitter <= 0:
        return base
    return base * random.uniform(1.0 - policy.jitter, 1.0 + policy.jitter)


def resilient_request(
    client: Any,
    method: str,
    url: str,
    *,
    gate: AdaptiveRequestGate,
    policy: RequestPolicy | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Issue a paced request and retry only failures that are safe to retry."""

    policy = policy or RequestPolicy()
    last_error: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        gate.acquire()
        gate.stats["requests"] += 1
        try:
            response = client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            last_error = exc
            gate.stats["network_errors"] += 1
            if attempt >= policy.max_attempts:
                raise
            delay = _backoff(policy, attempt)
            gate.stats["retries"] += 1
            gate.defer(delay)
            continue

        if response.status_code == 403:
            gate.stats["blocked"] += 1
            gate.defer(policy.forbidden_cooldown, block=True)
            raise ProviderBlockedError(
                f"{method.upper()} {url} returned 403; circuit opened for "
                f"{policy.forbidden_cooldown:.0f}s"
            )

        if response.status_code not in policy.retry_statuses:
            response.raise_for_status()
            return response

        if response.status_code == 429:
            gate.stats["rate_limited"] += 1
            delay = _retry_after(response)
            delay = _backoff(policy, attempt) if delay is None else delay
            delay = min(policy.max_retry_after, delay)
        else:
            gate.stats["server_errors"] += 1
            delay = _backoff(policy, attempt)

        last_error = httpx.HTTPStatusError(
            f"retryable upstream status {response.status_code}",
            request=response.request,
            response=response,
        )
        if attempt >= policy.max_attempts:
            raise last_error
        gate.stats["retries"] += 1
        gate.defer(delay)

    assert last_error is not None
    raise last_error
