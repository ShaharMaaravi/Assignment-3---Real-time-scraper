import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .sites import SiteDefinition

_ACCESSORY_WORDS = frozenset(
    {
        "adapter",
        "cable",
        "case",
        "charger",
        "cover",
        "dock",
        "keyboard",
        "mount",
        "pen",
        "pencil",
        "protector",
        "replacement",
        "skin",
        "sleeve",
        "stand",
        "stylus",
    }
)

_NULL_TEXT = frozenset({"", "n/a", "na", "none", "not available", "null", "unknown"})


@dataclass(frozen=True, slots=True)
class ProductFields:
    title: str | None
    price: str | None
    rating: float | None
    review_count: int | None

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if self.title is None or normalize_text(self.title).lower() in _NULL_TEXT:
            missing.append("product title")
        if (
            self.price is None
            or normalize_text(self.price).lower() in _NULL_TEXT
            or not re.search(r"\d", self.price)
        ):
            missing.append("price")
        if self.rating is None or not 0 <= self.rating <= 5:
            missing.append("average rating")
        if self.review_count is None or self.review_count < 0:
            missing.append("review count")
        return missing


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    title: str
    url: str
    score: float


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def _match_score(query: str, title: str) -> float:
    query_norm = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    title_norm = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    if not query_norm or not title_norm:
        return 0.0

    query_tokens = set(query_norm.split())
    title_tokens = set(title_norm.split())
    token_coverage = len(query_tokens & title_tokens) / len(query_tokens)
    sequence_score = SequenceMatcher(None, query_norm, title_norm).ratio()
    exact_bonus = 0.15 if query_norm in title_norm else 0.0
    accessory_penalty = 0.35 if _is_likely_accessory(query, title) else 0.0
    return max(
        0.0,
        min(
            1.0,
            0.65 * token_coverage + 0.35 * sequence_score + exact_bonus - accessory_penalty,
        ),
    )


def _is_likely_accessory(query: str, title: str) -> bool:
    query_tokens = set(re.sub(r"[^a-z0-9]+", " ", query.lower()).split())
    title_tokens = re.sub(r"[^a-z0-9]+", " ", title.lower()).split()
    unexpected_positions = [
        index
        for index, token in enumerate(title_tokens)
        if token in _ACCESSORY_WORDS and token not in query_tokens
    ]
    if not unexpected_positions:
        return False

    # Accessories usually lead the title ("Case for...", "Tab Pen..."). A genuine
    # bundle such as "Lenovo Tab P12 tablet with pen" names the requested product first.
    return min(unexpected_positions) <= 2


def is_product_match(query: str, title: str, minimum_score: float = 0.35) -> bool:
    """Return whether a scraped title is relevant enough and is not an accessory."""
    query_tokens = set(re.sub(r"[^a-z0-9]+", " ", query.lower()).split())
    title_tokens = set(re.sub(r"[^a-z0-9]+", " ", title.lower()).split())
    model_tokens = {
        token
        for token in query_tokens
        if any(character.isalpha() for character in token)
        and any(character.isdigit() for character in token)
    }
    if not model_tokens:
        model_tokens = {
            token
            for token in query_tokens
            if token.isdigit() and not (len(token) == 4 and 1900 <= int(token) <= 2099)
        }

    return (
        model_tokens <= title_tokens
        and not _is_likely_accessory(query, title)
        and _match_score(query, title) >= minimum_score
    )


def find_best_candidate(html: str, query: str, site: SiteDefinition) -> SearchCandidate:
    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[str, SearchCandidate] = {}

    for selector in site.result_link_selectors:
        for anchor in soup.select(selector):
            href = anchor.get("href")
            title = normalize_text(anchor.get_text(" ", strip=True))
            if not href or not title:
                continue
            url = urljoin(site.base_url, str(href))
            candidate = SearchCandidate(title=title, url=url, score=_match_score(query, title))
            previous = candidates.get(url)
            if previous is None or candidate.score > previous.score:
                candidates[url] = candidate

    if not candidates:
        raise ValueError("No product links were found on the search page")

    products = [
        candidate
        for candidate in candidates.values()
        if not _is_likely_accessory(query, candidate.title)
    ]
    if not products:
        raise ValueError("The search results contained only accessories")

    best = max(products, key=lambda candidate: candidate.score)
    if best.score < 0.35:
        raise ValueError("The search results did not contain a sufficiently similar product")
    return best


def _walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _first_value(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _parse_rating(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    rating = float(match.group())
    return rating if 0 <= rating <= 5 else None


def _parse_review_count(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d[\d,]*", str(value))
    return int(match.group().replace(",", "")) if match else None


def _format_price(value: Any, currency: Any = None) -> str | None:
    if value is None:
        return None
    raw = normalize_text(str(value))
    if not re.search(r"\d", raw):
        return None
    currency_text = normalize_text(str(currency)) if currency else ""
    if currency_text and currency_text.lower() not in raw.lower():
        return f"{raw} {currency_text}"
    return raw


def _product_from_json_ld(soup: BeautifulSoup) -> ProductFields | None:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            document = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue

        for node in _walk_json(document):
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]
            if "Product" not in types:
                continue

            offers = _first_value(node.get("offers")) or {}
            aggregate_rating = node.get("aggregateRating") or {}
            return ProductFields(
                title=normalize_text(str(node["name"])) if node.get("name") else None,
                price=_format_price(
                    offers.get("price") or offers.get("lowPrice"),
                    offers.get("priceCurrency"),
                ),
                rating=_parse_rating(aggregate_rating.get("ratingValue")),
                review_count=_parse_review_count(
                    aggregate_rating.get("reviewCount") or aggregate_rating.get("ratingCount")
                ),
            )
    return None


def _meta_content(soup: BeautifulSoup, *selectors: str) -> str | None:
    for selector in selectors:
        element = soup.select_one(selector)
        if not element:
            continue
        value = (
            element.get("content")
            or element.get("title")
            or element.get("aria-label")
            or element.get_text(" ", strip=True)
        )
        if value:
            return normalize_text(str(value))
    return None


def extract_product(html: str) -> ProductFields:
    soup = BeautifulSoup(html, "html.parser")
    structured = _product_from_json_ld(soup)

    title = (structured.title if structured else None) or _meta_content(
        soup,
        'meta[property="og:title"]',
        "#productTitle",
        "h1",
    )
    price = (structured.price if structured else None) or _format_price(
        _meta_content(
            soup,
            'meta[property="product:price:amount"]',
            '[itemprop="price"]',
            ".a-price .a-offscreen",
            ".priceView-customer-price span",
            ".price-current",
        ),
        _meta_content(soup, 'meta[property="product:price:currency"]'),
    )
    rating = (structured.rating if structured else None) or _parse_rating(
        _meta_content(
            soup,
            '[itemprop="ratingValue"]',
            "#acrPopover",
            ".a-icon-star .a-icon-alt",
            '[data-testid="reviews-and-ratings"]',
        )
    )
    review_count = (structured.review_count if structured else None) or _parse_review_count(
        _meta_content(soup, '[itemprop="reviewCount"]', '#acrCustomerReviewText')
    )

    return ProductFields(title=title, price=price, rating=rating, review_count=review_count)
