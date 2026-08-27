import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

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


class ScraperService:
    def __init__(
        self,
        strategy_factory: Callable[[httpx.AsyncClient], Sequence[ScrapeStrategy]] | None = None,
    ) -> None:
        self._strategy_factory = strategy_factory or (lambda client: (BasicScraper(client),))

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
            return list(
                await asyncio.gather(
                    *(self._scrape_site(site, normalized_query, strategies) for site in SITES)
                )
            )

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
                errors.append(f"{strategy.method.value}: {exc}")

        return ProductResult(
            website=site.name,
            status=ScrapeStatus.FAILED,
            method=ScrapeMethod.NOT_AVAILABLE,
            error="; ".join(errors) or "No scraping methods were configured",
        )
