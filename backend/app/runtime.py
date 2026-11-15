from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from .models import ProductResult
from .scraping import ScraperService


class SearchBusyError(RuntimeError):
    pass


class SearchDeadlineError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    max_concurrent_searches: int = 2
    queue_timeout_seconds: float = 2.0
    request_timeout_seconds: float = 100.0
    cache_ttl_seconds: float = 300.0
    rate_limit_requests: int = 5
    rate_limit_window_seconds: float = 60.0

    @classmethod
    def from_environment(cls) -> RuntimeSettings:
        raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
        origins = tuple(
            origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()
        )
        return cls(
            allowed_origins=origins or ("http://localhost:3000",),
            max_concurrent_searches=max(1, int(os.getenv("MAX_CONCURRENT_SEARCHES", "2"))),
            queue_timeout_seconds=max(0.1, float(os.getenv("QUEUE_TIMEOUT_SECONDS", "2"))),
            request_timeout_seconds=max(1.0, float(os.getenv("REQUEST_TIMEOUT_SECONDS", "100"))),
            cache_ttl_seconds=max(0.0, float(os.getenv("CACHE_TTL_SECONDS", "300"))),
            rate_limit_requests=max(1, int(os.getenv("RATE_LIMIT_REQUESTS", "5"))),
            rate_limit_window_seconds=max(
                1.0,
                float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
            ),
        )


class SearchRateLimiter:
    def __init__(
        self,
        maximum_requests: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._maximum_requests = maximum_requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, client_id: str) -> bool:
        now = self._clock()
        cutoff = now - self._window_seconds
        async with self._lock:
            timestamps = self._requests[client_id]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self._maximum_requests:
                return False
            timestamps.append(now)
            return True


class SearchCoordinator:
    def __init__(
        self,
        service: ScraperService,
        settings: RuntimeSettings,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._service = service
        self._settings = settings
        self._clock = clock
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_searches)
        self._cache: dict[str, tuple[float, list[ProductResult]]] = {}
        self._cache_lock = asyncio.Lock()

    async def search(self, query: str) -> tuple[list[ProductResult], bool]:
        cache_key = query.casefold()
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached, True

        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._settings.queue_timeout_seconds,
            )
        except TimeoutError as exc:
            raise SearchBusyError("The public demo is handling other searches") from exc

        try:
            try:
                results = await asyncio.wait_for(
                    self._service.search(query),
                    timeout=self._settings.request_timeout_seconds,
                )
            except TimeoutError as exc:
                raise SearchDeadlineError("The store search exceeded its time limit") from exc
        finally:
            self._semaphore.release()

        await self._store(cache_key, results)
        return results, False

    async def _get_cached(self, cache_key: str) -> list[ProductResult] | None:
        now = self._clock()
        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is None:
                return None
            expires_at, results = cached
            if expires_at <= now:
                self._cache.pop(cache_key, None)
                return None
            return results

    async def _store(self, cache_key: str, results: list[ProductResult]) -> None:
        if self._settings.cache_ttl_seconds <= 0:
            return
        expires_at = self._clock() + self._settings.cache_ttl_seconds
        async with self._cache_lock:
            self._cache[cache_key] = (expires_at, results)
