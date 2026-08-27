from enum import StrEnum

from pydantic import BaseModel, Field


class ScrapeStatus(StrEnum):
    SUCCESS = "Success"
    FAILED = "Failed"


class ScrapeMethod(StrEnum):
    BASIC = "Basic"
    BROWSER = "Browser"
    LLM = "LLM"
    FIRECRAWL = "Firecrawl"
    NOT_AVAILABLE = "N/A"


class ProductResult(BaseModel):
    website: str
    product_title: str | None = None
    price: str | None = None
    average_rating: float | None = None
    review_count: int | None = None
    status: ScrapeStatus
    method: ScrapeMethod
    product_url: str | None = None
    error: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)


class SearchResponse(BaseModel):
    query: str
    results: list[ProductResult]

