# Assignment 3 - Exercise 1

A real-time shopping comparison app with a FastAPI scraping backend and a Next.js frontend.

## Features

The complete backend and frontend flow is implemented:

- `POST /api/search` accepts a product query.
- Amazon, Best Buy, Walmart, and Newegg are searched concurrently.
- Search results are ranked for similarity before a product page is selected.
- Accessory results such as cases, chargers, and pens are rejected when the requested product
  is the device itself.
- Product data is extracted from JSON-LD first, with HTML metadata fallbacks.
- A failure on one website produces a failed result row instead of crashing the request.
- The fallback pipeline tries Basic scraping, Playwright, structured LLM extraction, and
  Firecrawl in the assignment's required order.
- A single Chromium process is reused during each search and cleaned up afterward.
- LLM and Firecrawl responses are validated against Pydantic schemas.
- Firecrawl uses its current v2 JSON extraction API and is attempted only after the first three
  methods fail.
- The responsive Next.js interface includes loading, network-error, success, and per-site failure
  states.
- The required results table shows website, title, price, rating, review count, status, and method.
- Product titles link to their source pages, and the cheapest result is highlighted only when
  successful stores report the same currency.

## Run the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
playwright install chromium
cp .env.example .env
# Add your OPENAI_API_KEY and FIRECRAWL_API_KEY to .env. Never commit that file.
uvicorn app.main:app --reload --env-file .env
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation.

## Run the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend uses `http://localhost:8000` by default. To use a
different backend URL, copy `.env.example` to `.env.local` and edit `NEXT_PUBLIC_API_URL`.

For a verified demonstration, search for `Logitech G502 HERO`.

## Test

```bash
cd backend
pytest

cd ../frontend
npm run lint
npm run build
```
