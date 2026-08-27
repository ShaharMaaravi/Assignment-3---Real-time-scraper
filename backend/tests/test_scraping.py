import httpx
import pytest

from app.extraction import ProductFields
from app.models import ScrapeMethod, ScrapeStatus
from app.scraping import LLMProductExtraction, LLMScraper, ScraperService
from app.sites import SITES


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
            assert kwargs["text_format"] is LLMProductExtraction
            return type(
                "Response",
                (),
                {
                    "output_parsed": LLMProductExtraction(
                        product_title="Example Product",
                        price="$99.00",
                        average_rating=4.5,
                        review_count=42,
                    )
                },
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
