"""Mechanical, config-driven search-query ingestion for the Source Bank.

The runner rotates enabled configured queries deterministically, fetches public
search results, and records them as ``status='new'`` Source Bank candidates.
It never judges relevance: the operator's existing source-review gate does that.
"""

from __future__ import annotations

import hashlib
import html
import os
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests


class _DuckDuckGoResultParser(HTMLParser):
    """Small mechanical parser for DuckDuckGo HTML result links and snippets."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._in_link = False
        self._in_snippet = False
        self._href = ""
        self._title: list[str] = []
        self._snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = attributes.get("class", "") or ""
        if tag == "a" and "result__a" in classes:
            self._in_link = True
            self._href = attributes.get("href", "") or ""
            self._title = []
        if tag in ("a", "div") and "result__snippet" in classes:
            self._in_snippet = True
            self._snippet = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link:
            title = " ".join("".join(self._title).split())
            url = self._result_url(self._href)
            if title and url:
                self.results.append({"title": title, "url": url, "summary": ""})
            self._in_link = False
        if tag in ("a", "div") and self._in_snippet:
            if self.results:
                self.results[-1]["summary"] = " ".join("".join(self._snippet).split())
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_link:
            self._title.append(data)
        if self._in_snippet:
            self._snippet.append(data)

    @staticmethod
    def _result_url(href: str) -> str:
        parsed = urlparse(html.unescape(href))
        redirect = parse_qs(parsed.query).get("uddg", [])
        return unquote(redirect[0]) if redirect else href


class QueryIngestionRunner:
    """Fetch and register a deterministic rotating subset of configured queries."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        self._init_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_table(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_slug TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT,
                    summary TEXT,
                    content TEXT,
                    origin TEXT NOT NULL DEFAULT 'system',
                    first_seen TEXT NOT NULL,
                    content_hash TEXT,
                    status TEXT NOT NULL DEFAULT 'active'
                );
                CREATE INDEX IF NOT EXISTS idx_sources_query_ingestion
                    ON sources(business_slug, content_hash);
            """)

    @staticmethod
    def select_queries(queries: list[dict], rotation: dict) -> list[dict]:
        """Select a stable, rotating subset without business-specific routing."""
        enabled = [item for item in queries if item.get("enabled", True)]
        if not enabled:
            return []
        per_cycle = max(1, min(int(rotation.get("per_cycle", len(enabled))), len(enabled)))
        seed = str(rotation.get("seed") or datetime.now(timezone.utc).strftime("%G-W%V"))
        ordered = sorted(
            enabled,
            key=lambda item: hashlib.sha256(
                f"{seed}\0{item.get('engine', '')}\0{item.get('query', '')}".encode()
            ).hexdigest(),
        )
        return ordered[:per_cycle]

    def _search(self, engine: str, query: str, date_window_months: int | None = None) -> list[dict]:
        if engine == "duckduckgo":
            response = requests.get(
                f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; ViralFactorySourceResearch/1.0)"},
                timeout=20,
            )
            response.raise_for_status()
            parser = _DuckDuckGoResultParser()
            parser.feed(response.text)
            return parser.results
        if engine == "exa":
            api_key = os.environ.get("EXA_API_KEY")
            if not api_key:
                return []
            payload = {"query": query, "numResults": 10, "contents": {"text": {"maxCharacters": 1200}}}
            response = requests.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return [
                {"title": item.get("title", ""), "url": item.get("url", ""),
                 "summary": item.get("text", "")[:1200]}
                for item in response.json().get("results", [])
            ]
        return []

    @staticmethod
    def _hash(result: dict) -> str:
        identity = result.get("url") or result.get("title", "")
        return hashlib.sha256(identity.encode()).hexdigest()[:16]

    def run(self, business_slug: str, queries: list[dict], rotation: dict) -> dict:
        selected = self.select_queries(queries, rotation)
        discovered = new = duplicates = 0
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for query in selected:
                try:
                    results = self._search(
                        str(query.get("engine", "")), str(query.get("query", "")),
                        query.get("date_window_months"),
                    )
                except requests.RequestException:
                    results = []
                for result in results:
                    if not result.get("title") or not result.get("url"):
                        continue
                    discovered += 1
                    content_hash = self._hash(result)
                    exists = conn.execute(
                        "SELECT 1 FROM sources WHERE business_slug=? AND content_hash=?",
                        (business_slug, content_hash),
                    ).fetchone()
                    if exists:
                        duplicates += 1
                        continue
                    conn.execute(
                        """INSERT INTO sources
                           (business_slug, source_type, title, url, summary, content, origin, first_seen, content_hash, status)
                           VALUES (?, 'search_item', ?, ?, ?, ?, 'system', ?, ?, 'new')""",
                        (business_slug, result["title"], result["url"], result.get("summary", ""),
                         result.get("summary", ""), now, content_hash),
                    )
                    new += 1
        return {"queries_selected": len(selected), "discovered": discovered, "new": new, "duplicates": duplicates}

    def list_ingested(self, business_slug: str) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(
                "SELECT * FROM sources WHERE business_slug=? AND source_type='search_item' ORDER BY id",
                (business_slug,),
            )]
