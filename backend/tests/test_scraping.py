import httpx

from app.extraction import ProductFields
from app.models import ScrapeMethod, ScrapeStatus
from app.scraping import ScraperService


class FailedStrategy:
    method = ScrapeMethod.BASIC

    async def scrape(self, site, query):
        raise RuntimeError("blocked")


class SuccessfulStrategy:
    method = ScrapeMethod.BROWSER

    async def scrape(self, site, query):
        return ProductFields("Example Product", "$99.00", 4.5, 42), f"{site.base_url}/product"


async def test_falls_back_and_keeps_each_site_independent() -> None:
    def strategies(_: httpx.AsyncClient):
        return (FailedStrategy(), SuccessfulStrategy())

    results = await ScraperService(strategy_factory=strategies).search("example product")

    assert len(results) == 4
    assert all(result.status is ScrapeStatus.SUCCESS for result in results)
    assert all(result.method is ScrapeMethod.BROWSER for result in results)


async def test_returns_clean_failure_when_every_method_fails() -> None:
    service = ScraperService(strategy_factory=lambda _: (FailedStrategy(),))

    results = await service.search("example product")

    assert len(results) == 4
    assert all(result.status is ScrapeStatus.FAILED for result in results)
    assert all(result.method is ScrapeMethod.NOT_AVAILABLE for result in results)
    assert all("blocked" in (result.error or "") for result in results)

