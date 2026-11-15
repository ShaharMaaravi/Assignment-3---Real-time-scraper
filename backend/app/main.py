from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .models import SearchRequest, SearchResponse
from .runtime import (
    RuntimeSettings,
    SearchBusyError,
    SearchCoordinator,
    SearchDeadlineError,
    SearchRateLimiter,
)
from .scraping import ScraperService

settings = RuntimeSettings.from_environment()
app = FastAPI(title="Real-time Shopping Scraper", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

scraper_service = ScraperService()
search_coordinator = SearchCoordinator(scraper_service, settings)
rate_limiter = SearchRateLimiter(
    settings.rate_limit_requests,
    settings.rate_limit_window_seconds,
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/search", response_model=SearchResponse)
async def search_products(
    request: SearchRequest,
    http_request: Request,
    response: Response,
) -> SearchResponse:
    forwarded_for = http_request.headers.get("x-forwarded-for", "")
    client_id = forwarded_for.split(",", 1)[0].strip()
    if not client_id:
        client_id = http_request.client.host if http_request.client else "unknown"
    if not await rate_limiter.allow(client_id):
        raise HTTPException(
            status_code=429,
            detail="Demo rate limit reached. Please wait one minute and try again.",
            headers={"Retry-After": str(round(settings.rate_limit_window_seconds))},
        )

    query = " ".join(request.query.split())
    try:
        results, cache_hit = await search_coordinator.search(query)
    except SearchBusyError as exc:
        raise HTTPException(
            status_code=503,
            detail="The demo is busy. Please try again shortly.",
            headers={"Retry-After": "5"},
        ) from exc
    except SearchDeadlineError as exc:
        raise HTTPException(
            status_code=504,
            detail="The retailers took too long to respond. Please try another query.",
        ) from exc
    response.headers["X-Market-Lens-Cache"] = "HIT" if cache_hit else "MISS"
    return SearchResponse(query=query, results=results)

