from app.extraction import extract_product, find_best_candidate
from app.sites import SITES


def test_selects_the_most_similar_product() -> None:
    html = """
    <div data-component-type="s-search-result">
      <h2><a href="/other">Generic tablet case</a></h2>
    </div>
    <div data-component-type="s-search-result">
      <h2><a href="/lenovo-p12">Lenovo Tab P12 2024 tablet 128GB</a></h2>
    </div>
    """

    result = find_best_candidate(html, "Lenovo Tab P12-2024", SITES[0])

    assert result.url == "https://www.amazon.com/lenovo-p12"
    assert result.score > 0.8


def test_does_not_prefer_an_accessory_with_more_query_tokens() -> None:
    html = """
    <a class="a-link-normal a-text-normal" href="/tablet/dp/1">
      Tab P12 128 GB 12.7 inch Mediatek 8 GB Wi-Fi tablet
    </a>
    <a class="a-link-normal a-text-normal" href="/case/dp/2">
      Protective case for Lenovo Tab P12 2024
    </a>
    """

    result = find_best_candidate(html, "Lenovo Tab P12-2024", SITES[0])

    assert result.url == "https://www.amazon.com/tablet/dp/1"


def test_extracts_product_from_json_ld() -> None:
    html = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Product",
      "name": "Lenovo Tab P12",
      "offers": {"@type": "Offer", "price": "332.54", "priceCurrency": "USD"},
      "aggregateRating": {"ratingValue": "4.7", "reviewCount": "1,315"}
    }
    </script>
    """

    result = extract_product(html)

    assert result.title == "Lenovo Tab P12"
    assert result.price == "332.54 USD"
    assert result.rating == 4.7
    assert result.review_count == 1315
