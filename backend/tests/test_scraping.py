import json

import httpx
import pytest

from app.extraction import ProductFields
from app.models import ScrapeMethod, ScrapeStatus
from app.scraping import (
    FirecrawlScraper,
    LLMProductExtraction,
    LLMScraper,
    ProductSelection,
    ScraperService,
)
from app.sites import SITES


class FailedStrategy:
    method = ScrapeMethod.BASIC

    async def scrape(self, site, query):
        raise RuntimeError("blocked")


class SuccessfulStrategy:
    method = ScrapeMethod.BROWSER

    async def scrape(self, site, query):
        return ProductFields(query, "$99.00", 4.5, 42), f"{site.base_url}/product"


class AccessoryStrategy:
    method = ScrapeMethod.BASIC

    async def scrape(self, site, query):
        title = "Tab Pen Plus compatible with Lenovo Tab P12"
        return ProductFields(title, "$29.00", 4.2, 31), f"{site.base_url}/pen"


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


async def test_rejects_accessory_results_and_uses_the_next_method() -> None:
    service = ScraperService(
        strategy_factory=lambda _: (AccessoryStrategy(), SuccessfulStrategy())
    )

    results = await service.search("Lenovo Tab P12-2024")

    assert len(results) == 4
    assert all(result.status is ScrapeStatus.SUCCESS for result in results)
    assert all(result.method is ScrapeMethod.BROWSER for result in results)


async def test_llm_scraper_requires_an_api_key_before_fetching() -> None:
    async with httpx.AsyncClient() as client:
        scraper = LLMScraper(client, api_key=None)

        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            await scraper.scrape(type("Site", (), {})(), "example product")


async def test_llm_scraper_parses_structured_product_data() -> None:
    search_html = """
    <div data-component-type="s-search-result">
      <h2><a href="/product">Example Product</a></h2>
    </div>
    """
    product_html = "<main>Example Product costs $99.00. Rated 4.5 by 42 customers.</main>"

    def handle_request(request: httpx.Request) -> httpx.Response:
        html = product_html if request.url.path == "/product" else search_html
        return httpx.Response(200, text=html)

    class FakeResponses:
        async def parse(self, **kwargs):
            if kwargs["text_format"] is ProductSelection:
                parsed = ProductSelection(
                    product_title="Example Product",
                    product_url="https://www.amazon.com/product",
                )
            else:
                assert kwargs["text_format"] is LLMProductExtraction
                parsed = LLMProductExtraction(
                    product_title="Example Product",
                    price="$99.00",
                    average_rating=4.5,
                    review_count=42,
                )
            return type(
                "Response",
                (),
                {"output_parsed": parsed},
            )()

    class FakeOpenAI:
        responses = FakeResponses()
        closed = False

        async def close(self):
            self.closed = True

    fake_openai = FakeOpenAI()
    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(transport=transport) as client:
        scraper = LLMScraper(client, api_key="test", openai_client=fake_openai)
        fields, product_url = await scraper.scrape(SITES[0], "Example Product")
        await scraper.close()

    assert fields == ProductFields("Example Product", "$99.00", 4.5, 42)
    assert product_url == "https://www.amazon.com/product"
    assert fake_openai.closed is True


async def test_firecrawl_scraper_requires_an_api_key() -> None:
    async with httpx.AsyncClient() as client:
        scraper = FirecrawlScraper(client, api_key=None)

        with pytest.raises(RuntimeError, match="FIRECRAWL_API_KEY"):
            await scraper.scrape(SITES[0], "Example Product")


async def test_firecrawl_selects_and_extracts_structured_product_data() -> None:
    requests: list[dict] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test"
        body = json.loads(request.content)
        requests.append(body)
        if "amazon.com/s" in body["url"]:
            extracted = {
                "product_title": "Example Product",
                "product_url": "https://www.amazon.com/product",
            }
        else:
            extracted = {
                "product_title": "Example Product",
                "price": "$99.00",
                "average_rating": 4.5,
                "review_count": 42,
            }
        return httpx.Response(200, json={"success": True, "data": {"json": extracted}})

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(transport=transport) as client:
        scraper = FirecrawlScraper(client, api_key="test")
        fields, product_url = await scraper.scrape(SITES[0], "Example Product")

    assert fields == ProductFields("Example Product", "$99.00", 4.5, 42)
    assert product_url == "https://www.amazon.com/product"
    assert len(requests) == 2
    assert requests[0]["onlyMainContent"] is False
    assert requests[1]["onlyMainContent"] is True
