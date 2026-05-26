from __future__ import annotations

import json
from typing import Any, Optional

from tools.polymarket import get_active_markets, get_prices
from tools.search import search_web

try:
    from crewai import Agent
    from crewai.tools import tool
except Exception:  # pragma: no cover - optional runtime dependency
    Agent = None  # type: ignore[assignment]
    tool = None  # type: ignore[assignment]


if tool:

    @tool("Get active Polymarket markets")
    def get_active_markets_tool(limit: int = 8) -> str:
        """Fetch active Polymarket Gamma markets as JSON."""
        return json.dumps(get_active_markets(limit=limit)[:limit])

    @tool("Get Polymarket CLOB prices")
    def get_prices_tool(market_id: str) -> str:
        """Fetch Polymarket CLOB midpoint data for a market/token identifier."""
        return json.dumps(get_prices(market_id))

    @tool("Search public web evidence")
    def search_web_tool(query: str) -> str:
        """Search public web evidence using Tavily when configured, else HTML search."""
        return json.dumps(search_web(query, max_results=5))

else:
    get_active_markets_tool = get_active_markets
    get_prices_tool = get_prices
    search_web_tool = search_web


def create_data_agent(llm: Optional[Any] = None) -> Any:
    if Agent is None:
        return None
    return Agent(
        role="Market Data",
        goal="Fetch Polymarket prices, volume, liquidity, and market metadata.",
        backstory=(
            "You are a low-level data agent. You never make trade decisions. "
            "You gather clean JSON facts for downstream analysts."
        ),
        tools=[get_active_markets_tool, get_prices_tool],
        llm=llm,
        verbose=True,
    )


def create_external_research_agent(llm: Optional[Any] = None) -> Any:
    if Agent is None:
        return None
    return Agent(
        role="External Research",
        goal="Find recent external evidence relevant to market resolution.",
        backstory=(
            "You are a news and source-gathering agent. You summarize evidence "
            "briefly and avoid unsupported claims."
        ),
        tools=[search_web_tool],
        llm=llm,
        verbose=True,
    )


def create_historical_agent(llm: Optional[Any] = None) -> Any:
    if Agent is None:
        return None
    return Agent(
        role="Historical Base Rate",
        goal="Estimate rough base rates from comparable resolved events.",
        backstory=(
            "You use simple historical analogies and clearly label uncertainty. "
            "When no data is available, you say so rather than inventing it."
        ),
        tools=[],
        llm=llm,
        verbose=True,
    )

