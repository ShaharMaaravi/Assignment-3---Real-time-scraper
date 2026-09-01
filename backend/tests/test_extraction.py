import pytest

from app.extraction import (
    ProductFields,
    extract_product,
    extract_search_candidate,
    find_best_candidate,
    is_product_match,
)
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


def test_candidate_selection_requires_the_exact_model_token() -> None:
    html = """
    <div data-component-type="s-search-result">
      <h2><a href="/2s">Logitech MX Master 2S Wireless Mouse</a></h2>
    </div>
    <div data-component-type="s-search-result">
      <h2><a href="/3s">Logitech MX Master 3S Performance Wireless Mouse</a></h2>
    </div>
    """

    result = find_best_candidate(html, "Logitech MX Master 3S", SITES[0])

    assert result.url == "https://www.amazon.com/3s"


def test_rejects_a_pen_that_mentions_the_requested_tablet() -> None:
    title = (
        "Tab Pen Plus for Lenovo Tab Pen Plus AP500U Compatible with Lenovo Tab M11, "
        "Tab P12, Tab K11 Plus"
    )

    assert not is_product_match("Lenovo Tab P12-2024", title)


def test_rejects_a_case_even_when_compatibility_text_says_tablet() -> None:
    title = 'Case for Lenovo Tab P12 (2024) 12.7" Tablet with Multi-Angle Stand Cover'

    assert not is_product_match("Lenovo Tab P12-2024", title)


def test_rejects_a_replacement_part_for_the_requested_model() -> None:
    title = "SOULWIT Hinge for Sony WH-1000XM5 - Black"

    assert not is_product_match("Sony WH-1000XM5", title)


def test_allows_a_requested_tablet_bundle_that_includes_a_pen() -> None:
    title = "Lenovo Tab P12 12.7-inch Tablet 128GB with Pen"

    assert is_product_match("Lenovo Tab P12-2024", title)


def test_requires_the_distinctive_model_token() -> None:
    title = 'Lenovo Idea Tab Plus 12.1" 2.5K Tablet 128GB'

    assert not is_product_match("Lenovo Tab P12-2024", title)


def test_literal_null_price_is_missing() -> None:
    fields = ProductFields("Lenovo Tab P12", "null", 4.7, 271)

    assert fields.missing_fields() == ["price"]


def test_extracts_best_buy_customer_price() -> None:
    html = """
    <script type="application/ld+json">
    {
      "@type": "Product",
      "name": "Recommended Product",
      "offers": {"price": "249.99", "priceCurrency": "USD"}
    }
    </script>
    <h1>Logitech MX Master 3S</h1>
    <div data-testid="price-block-customer-price">
      <span class="sr-only">$84.99</span><span aria-hidden="true">$ 84 99</span>
    </div>
    """

    assert extract_product(html).price == "$84.99"


def test_ignores_an_amazon_recommendation_price_outside_the_buy_box() -> None:
    html = """
    <h1 id="productTitle">Sony WH-1000XM5 Headphones</h1>
    <section class="recommendations">
      <span class="a-price"><span class="a-offscreen">$19.99</span></span>
    </section>
    """

    assert extract_product(html).price is None


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


def test_extracts_facts_from_the_selected_amazon_search_card() -> None:
    html = """
    <div data-component-type="s-search-result">
      <h2><a href="/sony/dp/000">Sony WH-1000XM5 Headphones</a></h2>
      <span class="a-icon-star-small"><span class="a-icon-alt">4.5 out of 5 stars</span></span>
      <a href="/sony/dp/000#customerReviews"><span class="s-underline-text">2,000</span></a>
    </div>
    <div data-component-type="s-search-result">
      <h2><a href="/wrong/dp/111">Sony headphone case</a></h2>
      <span class="a-price"><span class="a-offscreen">$19.99</span></span>
    </div>
    <div data-component-type="s-search-result">
      <h2><a href="/sony/dp/222/ref=sr_1_2">Sony WH-1000XM5 Headphones</a></h2>
      <span class="a-price"><span class="a-offscreen">$248.00</span></span>
      <span class="a-icon-star-small"><span class="a-icon-alt">4.3 out of 5 stars</span></span>
      <a href="/sony/dp/222#customerReviews"><span class="s-underline-text">1,413</span></a>
    </div>
    """

    fields, url = extract_search_candidate(html, "Sony WH-1000XM5", SITES[0])

    assert fields == ProductFields("Sony WH-1000XM5 Headphones", "$248.00", 4.3, 1413)
    assert url == "https://www.amazon.com/sony/dp/222/ref=sr_1_2"
