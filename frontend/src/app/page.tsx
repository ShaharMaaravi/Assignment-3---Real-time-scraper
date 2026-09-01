"use client";

import { FormEvent, useMemo, useState } from "react";
import styles from "./page.module.css";

type ScrapeStatus = "Success" | "Failed";
type ScrapeMethod = "Basic" | "Browser" | "LLM" | "Firecrawl" | "N/A";

type ProductResult = {
  website: string;
  product_title: string | null;
  price: string | null;
  average_rating: number | null;
  review_count: number | null;
  status: ScrapeStatus;
  method: ScrapeMethod;
  product_url: string | null;
  error: string | null;
};

type SearchResponse = {
  query: string;
  results: ProductResult[];
};

type ParsedPrice = {
  amount: number;
  currency: string;
};

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

const STORE_CODES: Record<string, string> = {
  "Amazon.com": "AM",
  "BestBuy.com": "BB",
  "Walmart.com": "WM",
  "Newegg.com": "NE",
};

function parsePrice(value: string | null): ParsedPrice | null {
  if (!value) return null;

  const normalized = value.replace(/,/g, "").trim();
  const number = normalized.match(/\d+(?:\.\d+)?/);
  if (!number) return null;

  let currency = "";
  if (/\bILS\b|₪/i.test(normalized)) currency = "ILS";
  else if (/\bUSD\b|\$/i.test(normalized)) currency = "USD";
  else if (/\bEUR\b|€/i.test(normalized)) currency = "EUR";
  else if (/\bGBP\b|£/i.test(normalized)) currency = "GBP";

  const amount = Number(number[0]);
  return Number.isFinite(amount) ? { amount, currency } : null;
}

function findBestPriceWebsite(results: ProductResult[]): string | null {
  const prices = results
    .filter((result) => result.status === "Success")
    .map((result) => ({ result, parsed: parsePrice(result.price) }))
    .filter(
      (entry): entry is { result: ProductResult; parsed: ParsedPrice } =>
        entry.parsed !== null,
    );

  if (prices.length < 2) return null;
  const currencies = new Set(prices.map((entry) => entry.parsed.currency));
  if (currencies.size !== 1) return null;

  return prices.reduce((best, current) =>
    current.parsed.amount < best.parsed.amount ? current : best,
  ).result.website;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bestPriceWebsite = useMemo(
    () => (response ? findBestPriceWebsite(response.results) : null),
    [response],
  );
  const successCount = response?.results.filter((result) => result.status === "Success").length ?? 0;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (normalizedQuery.length < 2) {
      setError("Enter at least two characters to search.");
      return;
    }

    setIsLoading(true);
    setError(null);
    setResponse(null);

    try {
      const apiResponse = await fetch(`${API_URL}/api/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: normalizedQuery }),
      });

      if (!apiResponse.ok) {
        throw new Error(`The search service returned HTTP ${apiResponse.status}.`);
      }

      const data = (await apiResponse.json()) as SearchResponse;
      if (!Array.isArray(data.results)) {
        throw new Error("The search service returned an unexpected response.");
      }
      setResponse(data);
    } catch (requestError) {
      const message =
        requestError instanceof Error ? requestError.message : "The search could not be completed.";
      setError(`${message} Make sure the FastAPI backend is running at ${API_URL}.`);
    } finally {
      setIsLoading(false);
    }
  }

  function useDemoQuery() {
    setQuery("Logitech G502 HERO");
    setError(null);
  }

  return (
    <main className={styles.pageShell}>
      <div className={styles.ambientOne} aria-hidden="true" />
      <div className={styles.ambientTwo} aria-hidden="true" />

      <section className={styles.hero}>
        <nav className={styles.nav} aria-label="Main navigation">
          <a className={styles.brand} href="#top" aria-label="Market Lens home">
            <span className={styles.brandMark}>ML</span>
            <span>Market Lens</span>
          </a>
          <span className={styles.liveBadge}>
            <span className={styles.liveDot} aria-hidden="true" />
            Real-time comparison
          </span>
        </nav>

        <div className={styles.heroCopy} id="top">
          <p className={styles.eyebrow}>SHOP SMARTER ACROSS THE WEB</p>
          <h1>
            One search.
            <br />
            Four stores. <span>Clear answers.</span>
          </h1>
          <p className={styles.intro}>
            Compare live product prices, ratings, and reviews from Amazon, Best Buy,
            Walmart, and Newegg—without opening a dozen tabs.
          </p>
        </div>

        <form className={styles.searchPanel} onSubmit={handleSubmit}>
          <label htmlFor="product-query">What product are you looking for?</label>
          <div className={styles.searchRow}>
            <div className={styles.inputWrap}>
              <span className={styles.searchIcon} aria-hidden="true">⌕</span>
              <input
                id="product-query"
                name="query"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="e.g. Logitech G502 HERO"
                minLength={2}
                maxLength={200}
                autoComplete="off"
                disabled={isLoading}
              />
            </div>
            <button type="submit" disabled={isLoading}>
              {isLoading ? "Searching…" : "Find product"}
            </button>
          </div>
          <button className={styles.demoQuery} type="button" onClick={useDemoQuery}>
            Try the verified demo: <strong>Logitech G502 HERO</strong>
          </button>
        </form>
      </section>

      <section className={styles.resultsSection} aria-live="polite" aria-busy={isLoading}>
        {error && <div className={styles.errorBanner} role="alert">{error}</div>}

        {isLoading && (
          <div className={styles.loadingCard}>
            <div className={styles.loader} aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
            </div>
            <div>
              <h2>Searching four stores in parallel</h2>
              <p>Blocked pages automatically move through the fallback pipeline. This can take a minute.</p>
            </div>
          </div>
        )}

        {!isLoading && response && (
          <>
            <div className={styles.resultsHeader}>
              <div>
                <p className={styles.sectionLabel}>LIVE RESULTS</p>
                <h2>Comparison for “{response.query}”</h2>
              </div>
              <div className={styles.summaryPills}>
                <span><strong>{successCount}</strong> successful</span>
                <span><strong>{response.results.length - successCount}</strong> failed</span>
              </div>
            </div>

            <div className={styles.tableFrame}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Website</th>
                    <th scope="col">Product title</th>
                    <th scope="col">Price</th>
                    <th scope="col">Average rating</th>
                    <th scope="col">Review count</th>
                    <th scope="col">Status</th>
                    <th scope="col">Method</th>
                  </tr>
                </thead>
                <tbody>
                  {response.results.map((result) => {
                    const isBestPrice = result.website === bestPriceWebsite;
                    return (
                      <tr key={result.website} className={isBestPrice ? styles.bestPriceRow : undefined}>
                        <td data-label="Website">
                          <div className={styles.storeCell}>
                            <span className={styles.storeMark} aria-hidden="true">
                              {STORE_CODES[result.website] ?? result.website.slice(0, 2).toUpperCase()}
                            </span>
                            <strong>{result.website}</strong>
                          </div>
                        </td>
                        <td data-label="Product title" className={styles.productCell}>
                          {result.product_title ? (
                            result.product_url ? (
                              <a href={result.product_url} target="_blank" rel="noreferrer">
                                {result.product_title}<span aria-hidden="true"> ↗</span>
                              </a>
                            ) : result.product_title
                          ) : (
                            <>
                              <span className={styles.muted}>No valid product returned</span>
                              {result.error && (
                                <details>
                                  <summary>View failure reason</summary>
                                  <p>{result.error}</p>
                                </details>
                              )}
                            </>
                          )}
                        </td>
                        <td data-label="Price">
                          <div className={styles.priceCell}>
                            <strong>{result.price ?? "—"}</strong>
                            {isBestPrice && <span className={styles.bestPrice}>Best price</span>}
                          </div>
                        </td>
                        <td data-label="Average rating">
                          {result.average_rating !== null ? (
                            <span className={styles.rating}>★ {result.average_rating.toFixed(1)}</span>
                          ) : "—"}
                        </td>
                        <td data-label="Review count">{result.review_count?.toLocaleString() ?? "—"}</td>
                        <td data-label="Status">
                          <span className={`${styles.status} ${result.status === "Success" ? styles.success : styles.failed}`}>
                            {result.status}
                          </span>
                        </td>
                        <td data-label="Method"><span className={styles.method}>{result.method}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {bestPriceWebsite && (
              <p className={styles.priceNote}>
                Best price is highlighted only when successful stores report the same currency.
              </p>
            )}
          </>
        )}

        {!isLoading && !response && !error && (
          <div className={styles.featureGrid}>
            <article>
              <span>01</span>
              <h2>Exact-match safeguards</h2>
              <p>Model-aware ranking rejects accessories, repair parts, and unrelated variants.</p>
            </article>
            <article>
              <span>02</span>
              <h2>Four-layer fallback</h2>
              <p>Basic HTML, browser rendering, LLM extraction, and Firecrawl work in sequence.</p>
            </article>
            <article>
              <span>03</span>
              <h2>Failure isolation</h2>
              <p>One blocked store never prevents valid results from the other retailers.</p>
            </article>
          </div>
        )}
      </section>

      <footer className={styles.footer}>
        <span>Market Lens</span>
        <span>Real-time shopping intelligence</span>
      </footer>
    </main>
  );
}
