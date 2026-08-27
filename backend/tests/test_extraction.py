import pytest

from app.extraction import ProductFields, extract_product, find_best_candidate, is_product_match
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


def test_rejects_a_pen_that_mentions_the_requested_tablet() -> None:
    title = (
        "Tab Pen Plus for Lenovo Tab Pen Plus AP500U Compatible with Lenovo Tab M11, "
        "Tab P12, Tab K11 Plus"
    )

    assert not is_product_match("Lenovo Tab P12-2024", title)


def test_rejects_a_case_even_when_compatibility_text_says_tablet() -> None:
    title = 'Case for Lenovo Tab P12 (2024) 12.7" Tablet with Multi-Angle Stand Cover'

    assert not is_product_match("Lenovo Tab P12-2024", title)


def test_allows_a_requested_tablet_bundle_that_includes_a_pen() -> None:
    title = "Lenovo Tab P12 12.7-inch Tablet 128GB with Pen"

    assert is_product_match("Lenovo Tab P12-2024", title)


def test_requires_the_distinctive_model_token() -> None:
    title = 'Lenovo Idea Tab Plus 12.1" 2.5K Tablet 128GB'

    assert not is_product_match("Lenovo Tab P12-2024", title)


def test_literal_null_price_is_missing() -> None:
    fields = ProductFields("Lenovo Tab P12", "null", 4.7, 271)

    assert fields.missing_fields() == ["price"]


def test_search_fails_cleanly_when_every_result_is_an_accessory() -> None:
    html = """
    <div data-component-type="s-search-result">
      <h2><a href="/pen">Tab Pen Plus compatible with Lenovo Tab P12</a></h2>
    </div>
    """

    with pytest.raises(ValueError, match="only accessories"):
        find_best_candidate(html, "Lenovo Tab P12-2024", SITES[0])


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
