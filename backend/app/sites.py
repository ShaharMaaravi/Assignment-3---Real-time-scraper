from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True, slots=True)
class SiteDefinition:
    name: str
    base_url: str
    search_url_template: str
    result_link_selectors: tuple[str, ...]

    def search_url(self, query: str) -> str:
        return self.search_url_template.format(query=quote_plus(query))


SITES: tuple[SiteDefinition, ...] = (
    SiteDefinition(
        name="Amazon.com",
        base_url="https://www.amazon.com",
        search_url_template="https://www.amazon.com/s?k={query}",
        result_link_selectors=(
            '[data-component-type="s-search-result"] h2 a',
            "a.a-link-normal.s-no-outline",
        ),
    ),
    SiteDefinition(
        name="BestBuy.com",
        base_url="https://www.bestbuy.com",
        search_url_template="https://www.bestbuy.com/site/searchpage.jsp?st={query}",
        result_link_selectors=(".sku-item .sku-title a", "h4.sku-title a"),
    ),
    SiteDefinition(
        name="Walmart.com",
        base_url="https://www.walmart.com",
        search_url_template="https://www.walmart.com/search?q={query}",
        result_link_selectors=(
            'a[link-identifier="linkText"]',
            'a[href*="/ip/"]',
        ),
    ),
    SiteDefinition(
        name="Newegg.com",
        base_url="https://www.newegg.com",
        search_url_template="https://www.newegg.com/p/pl?d={query}",
        result_link_selectors=(".item-cell .item-title", "a.item-title"),
    ),
)

