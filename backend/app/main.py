from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .models import SearchRequest, SearchResponse
from .scraping import ScraperService

app = FastAPI(title="Real-time Shopping Scraper", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scraper_service = ScraperService()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/search", response_model=SearchResponse)
async def search_products(request: SearchRequest) -> SearchResponse:
    query = " ".join(request.query.split())
    results = await scraper_service.search(query)
    return SearchResponse(query=query, results=results)

