import asyncio

import pytest

from app.models import ProductResult, ScrapeMethod, ScrapeStatus
from app.runtime import (
    RuntimeSettings,
    SearchBusyError,
    SearchCoordinator,
    SearchDeadlineError,
    SearchRateLimiter,
)


def result() -> ProductResult:
    return ProductResult(
        website="Example.com",
        product_title="Example Product",
        price="$99",
        average_rating=4.5,
        review_count=42,
        status=ScrapeStatus.SUCCESS,
        method=ScrapeMethod.BASIC,
        product_url="https://example.com/product",
    )


class CountingService:
    def __init__(self, delay: float = 0.0) -> None:
        self.calls = 0
        self.delay = delay

    async def search(self, query: str) -> list[ProductResult]:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return [result()]


async def test_coordinator_caches_normalized_queries() -> None:
    service = CountingService()
    settings = RuntimeSettings(cache_ttl_seconds=60)
    coordinator = SearchCoordinator(service, settings)

    first, first_cached = await coordinator.search("Example Product")
    second, second_cached = await coordinator.search("example product")

    assert first == second
    assert first_cached is False
    assert second_cached is True
    assert service.calls == 1


async def test_coordinator_times_out_slow_searches() -> None:
    service = CountingService(delay=0.05)
    settings = RuntimeSettings(request_timeout_seconds=0.01)
    coordinator = SearchCoordinator(service, settings)

    with pytest.raises(SearchDeadlineError):
        await coordinator.search("Example Product")


async def test_coordinator_rejects_when_capacity_is_busy() -> None:
    service = CountingService(delay=0.05)
    settings = RuntimeSettings(
        max_concurrent_searches=1,
        queue_timeout_seconds=0.01,
        request_timeout_seconds=1,
    )
    coordinator = SearchCoordinator(service, settings)
    active = asyncio.create_task(coordinator.search("First"))
    await asyncio.sleep(0)

    with pytest.raises(SearchBusyError):
        await coordinator.search("Second")
    await active


async def test_rate_limiter_enforces_a_sliding_window() -> None:
    now = 100.0
    limiter = SearchRateLimiter(2, 60, clock=lambda: now)

    assert await limiter.allow("client") is True
    assert await limiter.allow("client") is True
    assert await limiter.allow("client") is False
    now = 161.0
    assert await limiter.allow("client") is True
