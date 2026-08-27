import asyncio
import inspect
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .extraction import ProductFields, extract_product, find_best_candidate
from .models import ProductResult, ScrapeMethod, ScrapeStatus
from .sites import SITES, SiteDefinition


class ScrapeStrategy(Protocol):
    method: ScrapeMethod

    async def scrape(self, site: SiteDefinition, query: str) -> tuple[ProductFields, str]: ...


@dataclass(slots=True)
class BasicScraper:
    client: httpx.AsyncClient
    method: ScrapeMethod = ScrapeMethod.BASIC

    async def scrape(self, site: SiteDefinition, query: str) -> tuple[ProductFields, str]:
        search_response = await self.client.get(site.search_url(query))
        search_response.raise_for_status()
        candidate = find_best_candidate(search_response.text, query, site)

        product_response = await self.client.get(candidate.url)
        product_response.raise_for_status()
        return extract_product(product_response.text), candidate.url


@dataclass(slots=True)
class BrowserScraper:
    method: ScrapeMethod = ScrapeMethod.BROWSER
    navigation_timeout_ms: int = 30_000
    settle_delay_ms: int = 1_500
    _startup_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _playwright: Any = field(default=None, init=False)
    _browser: Any = field(default=None, init=False)

    async def _ensure_browser(self) -> Any:
        if self._browser is not None:
            return self._browser

        async with self._startup_lock:
            if self._browser is not None:
                return self._browser

            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            try:
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception:
                await self._playwright.stop()
                self._playwright = None
                raise
            return self._browser

    async def scrape(self, site: SiteDefinition, query: str) -> tuple[ProductFields, str]:
        browser = await self._ensure_browser()
        page = await browser.new_page(
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page.set_default_navigation_timeout(self.navigation_timeout_ms)

        try:
            await self._navigate(page, site.search_url(query))
            candidate = find_best_candidate(await page.content(), query, site)

            await self._navigate(page, candidate.url)
            return extract_product(await page.content()), candidate.url
        finally:
            await page.close()

    async def _navigate(self, page: Any, url: str) -> None:
        response = await page.goto(url, wait_until="domcontentloaded")
        if response is not None and not response.ok:
            raise RuntimeError(f"Browser received HTTP {response.status} for {url}")
        await page.wait_for_timeout(self.settle_delay_ms)

    async def close(self) -> None:
        browser, playwright = self._browser, self._playwright
        self._browser = None
        self._playwright = None
        if browser is not None:
            with suppress(Exception):
                await browser.close()
        if playwright is not None:
            with suppress(Exception):
                await playwright.stop()


def _describe_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message or type(exc).__name__


class ScraperService:
    def __init__(
        self,
        strategy_factory: Callable[[httpx.AsyncClient], Sequence[ScrapeStrategy]] | None = None,
    ) -> None:
        self._strategy_factory = strategy_factory or (
            lambda client: (BasicScraper(client), BrowserScraper())
        )

    async def search(self, query: str) -> list[ProductResult]:
        normalized_query = " ".join(query.split())
        timeout = httpx.Timeout(15.0, connect=8.0)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
        ) as client:
            strategies = tuple(self._strategy_factory(client))
            try:
                return list(
                    await asyncio.gather(
                        *(self._scrape_site(site, normalized_query, strategies) for site in SITES)
                    )
                )
            finally:
                await self._close_strategies(strategies)

    async def _close_strategies(self, strategies: Sequence[ScrapeStrategy]) -> None:
        for strategy in strategies:
            close = getattr(strategy, "close", None)
            if close is None:
                continue
            result = close()
            if inspect.isawaitable(result):
                await result

    async def _scrape_site(
        self,
        site: SiteDefinition,
        query: str,
        strategies: Sequence[ScrapeStrategy],
    ) -> ProductResult:
        errors: list[str] = []
        for strategy in strategies:
            try:
                fields, product_url = await strategy.scrape(site, query)
                missing = fields.missing_fields()
                if missing:
                    raise ValueError(f"Missing required fields: {', '.join(missing)}")
                return ProductResult(
                    website=site.name,
                    product_title=fields.title,
                    price=fields.price,
                    average_rating=fields.rating,
                    review_count=fields.review_count,
                    status=ScrapeStatus.SUCCESS,
                    method=strategy.method,
                    product_url=product_url,
                )
            # A third-party scraper can fail in unexpected ways. Isolation is a core API promise.
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{strategy.method.value}: {_describe_error(exc)}")

        return ProductResult(
            website=site.name,
            status=ScrapeStatus.FAILED,
            method=ScrapeMethod.NOT_AVAILABLE,
            error="; ".join(errors) or "No scraping methods were configured",
        )
