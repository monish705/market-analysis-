from __future__ import annotations

import logging
import time
from typing import Dict, List
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT_SECONDS, REQUEST_SLEEP_SECONDS, TAVILY_API_KEY

logger = logging.getLogger(__name__)


def tavily_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    if not TAVILY_API_KEY:
        return []

    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
        }
        for item in payload.get("results", [])
    ]


def duckduckgo_html_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {"User-Agent": "Mozilla/5.0 pyramid-prototype/0.1"}
    response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    results: List[Dict[str, str]] = []
    for row in soup.select(".result"):
        title_node = row.select_one(".result__a")
        snippet_node = row.select_one(".result__snippet")
        if not title_node:
            continue
        results.append(
            {
                "title": title_node.get_text(" ", strip=True),
                "url": title_node.get("href", ""),
                "content": snippet_node.get_text(" ", strip=True)
                if snippet_node
                else "",
            }
        )
        if len(results) >= max_results:
            break
    return results


def search_web(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    time.sleep(REQUEST_SLEEP_SECONDS)
    try:
        results = tavily_search(query, max_results=max_results)
        if results:
            return results
    except Exception as exc:
        logger.debug("Tavily search failed, falling back to HTML search: %s", exc)

    try:
        return duckduckgo_html_search(query, max_results=max_results)
    except Exception as exc:
        logger.warning("Search failed for query %r: %s", query, exc)
        return []

