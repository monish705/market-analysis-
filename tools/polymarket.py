from __future__ import annotations

import json
import logging
import socket
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

from config import (
    HTTP_TIMEOUT_SECONDS,
    MIN_VOLUME_USD,
    POLYMARKET_MAX_ATTEMPTS,
    POLYMARKET_CLOB_URL,
    POLYMARKET_GAMMA_URL,
    POLYMARKET_PUBLIC_DNS_FALLBACK,
    POLYMARKET_PUBLIC_IPS,
    REQUEST_SLEEP_SECONDS,
)
from risk import MarketSnapshot

logger = logging.getLogger(__name__)


class PolymarketAPIError(RuntimeError):
    pass


def _session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "polymarket-pyramid-prototype/0.2",
        }
    )
    return session


@contextmanager
def _public_dns_override(hostname: str):
    if not POLYMARKET_PUBLIC_DNS_FALLBACK or hostname not in {
        "gamma-api.polymarket.com",
        "clob.polymarket.com",
    }:
        yield
        return

    original_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(host: str, port: int, family=0, type=0, proto=0, flags=0):
        if host == hostname:
            results = []
            for ip in POLYMARKET_PUBLIC_IPS:
                results.extend(
                    original_getaddrinfo(ip, port, socket.AF_INET, type, proto, flags)
                )
            return results
        return original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = patched_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


def _get_json(url: str, params: Dict[str, Any]) -> Any:
    hostname = urlparse(url).hostname or ""
    last_error: Exception | None = None

    for attempt in range(1, POLYMARKET_MAX_ATTEMPTS + 1):
        try:
            with _public_dns_override(hostname):
                response = _session().get(
                    url,
                    params=params,
                    timeout=HTTP_TIMEOUT_SECONDS,
                )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                raise PolymarketAPIError(f"Invalid JSON from {url}") from exc
        except Exception as exc:
            last_error = exc
            if attempt == POLYMARKET_MAX_ATTEMPTS:
                break
            backoff = min(attempt, 3)
            logger.warning(
                "Polymarket request failed (%s/%s): %s; retrying in %ss",
                attempt,
                POLYMARKET_MAX_ATTEMPTS,
                exc,
                backoff,
            )
            time.sleep(backoff)

    raise PolymarketAPIError(f"Polymarket request failed after retries: {last_error}")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def get_active_markets(limit: int = 10) -> List[Dict[str, Any]]:
    try:
        markets = get_active_markets_from_events(limit=limit)
        if markets:
            return markets[:limit]
    except Exception as exc:
        logger.warning("Gamma /events failed, trying /markets fallback: %s", exc)

    data = _get_json(
        f"{POLYMARKET_GAMMA_URL}/markets",
        params={
            "active": "true",
            "closed": "false",
            "archived": "false",
            "order": "volume_24hr",
            "ascending": "false",
            "limit": max(limit * 5, 25),
        },
    )
    if isinstance(data, dict) and "markets" in data:
        markets = data["markets"]
    elif isinstance(data, list):
        markets = data
    else:
        raise ValueError(f"Unexpected Gamma response shape: {type(data).__name__}")

    open_markets = [
        market
        for market in markets
        if _is_open_market(market) and _passes_market_filters(market)
    ]
    return open_markets[:limit]


def get_active_markets_from_events(limit: int = 10) -> List[Dict[str, Any]]:
    events = _get_json(
        f"{POLYMARKET_GAMMA_URL}/events",
        params={
            "active": "true",
            "closed": "false",
            "order": "volume_24hr",
            "ascending": "false",
            "limit": max(limit * 5, 25),
        },
    )
    if isinstance(events, dict) and "events" in events:
        events = events["events"]
    if not isinstance(events, list):
        raise ValueError(f"Unexpected Gamma events response shape: {type(events).__name__}")

    markets: List[Dict[str, Any]] = []
    for event in events:
        for market in event.get("markets", []) or []:
            market.setdefault("category", event.get("category"))
            market.setdefault("eventSlug", event.get("slug"))
            market.setdefault("eventVolume24hr", event.get("volume24hr"))
            market.setdefault("eventLiquidity", event.get("liquidity"))
            if _is_open_market(market) and _passes_market_filters(market):
                markets.append(market)
            if len(markets) >= limit:
                return markets
    return markets


def get_prices(market_id: str) -> Dict[str, Any]:
    # CLOB midpoint endpoint is token-centric on current Polymarket deployments.
    # This market-id form is kept because it is useful for quick endpoint probes.
    payload = _get_json(
        f"{POLYMARKET_CLOB_URL}/midpoint",
        params={"market": market_id},
    )
    return payload


def get_token_midpoint(token_id: str) -> Optional[float]:
    if not token_id:
        return None
    try:
        payload = _get_json(
            f"{POLYMARKET_CLOB_URL}/midpoint",
            params={"token_id": token_id},
        )
        midpoint = payload.get("mid") or payload.get("midpoint")
        return _safe_float(midpoint, default=None)  # type: ignore[arg-type]
    except Exception as exc:
        logger.debug("CLOB midpoint lookup failed for token %s: %s", token_id, exc)
        return None


def _is_open_market(market: Dict[str, Any]) -> bool:
    return (
        market.get("active") is not False
        and market.get("closed") is not True
        and market.get("archived") is not True
    )


def _volume_24hr(market: Dict[str, Any]) -> float:
    return _safe_float(
        market.get("volume24hr")
        or market.get("volume_24hr")
        or market.get("volume24hrClob")
        or market.get("eventVolume24hr")
        or market.get("volumeNum")
        or market.get("volume")
    )


def _liquidity_value(market: Dict[str, Any]) -> float:
    return _safe_float(
        market.get("liquidityNum")
        or market.get("liquidity")
        or market.get("liquidityClob")
        or market.get("eventLiquidity")
    )


def _passes_market_filters(market: Dict[str, Any]) -> bool:
    volume_ok = _volume_24hr(market) > MIN_VOLUME_USD
    token_ids = _parse_jsonish(market.get("clobTokenIds")) or []
    has_clob = isinstance(token_ids, list) and len(token_ids) >= 2
    liquidity_ok = _liquidity_value(market) > 0 or has_clob
    return volume_ok and liquidity_ok


def normalize_market(raw: Dict[str, Any], enrich_clob: bool = True) -> MarketSnapshot:
    outcomes = _parse_jsonish(raw.get("outcomes")) or []
    outcome_prices = _parse_jsonish(raw.get("outcomePrices")) or []
    token_ids = _parse_jsonish(raw.get("clobTokenIds")) or []

    yes_index = 0
    no_index = 1
    if isinstance(outcomes, list):
        lowered = [str(item).lower() for item in outcomes]
        if "yes" in lowered:
            yes_index = lowered.index("yes")
        if "no" in lowered:
            no_index = lowered.index("no")

    yes_price = None
    no_price = None
    if isinstance(outcome_prices, list) and outcome_prices:
        if len(outcome_prices) > yes_index:
            yes_price = _safe_float(outcome_prices[yes_index], default=None)  # type: ignore[arg-type]
        if len(outcome_prices) > no_index:
            no_price = _safe_float(outcome_prices[no_index], default=None)  # type: ignore[arg-type]

    yes_token_id = None
    no_token_id = None
    if isinstance(token_ids, list):
        if len(token_ids) > yes_index:
            yes_token_id = str(token_ids[yes_index])
        if len(token_ids) > no_index:
            no_token_id = str(token_ids[no_index])

    if enrich_clob and yes_token_id:
        time.sleep(REQUEST_SLEEP_SECONDS)
        clob_yes = get_token_midpoint(yes_token_id)
        if clob_yes is not None and 0 <= clob_yes <= 1:
            yes_price = clob_yes
            no_price = round(1.0 - clob_yes, 4)

    market_id = str(raw.get("id") or raw.get("conditionId") or raw.get("slug"))
    slug = raw.get("slug")
    return MarketSnapshot(
        id=market_id,
        question=str(raw.get("question") or raw.get("title") or "Untitled market"),
        slug=slug,
        condition_id=raw.get("conditionId"),
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
        yes_price=yes_price,
        no_price=no_price,
        volume=_safe_float(
            raw.get("volume24hr")
            or raw.get("volume_24hr")
            or raw.get("volume24hrClob")
            or raw.get("eventVolume24hr")
            or raw.get("volumeNum")
            or raw.get("volume")
            or raw.get("volumeClob")
        ),
        liquidity=_liquidity_value(raw),
        end_date=raw.get("endDate") or raw.get("endDateIso"),
        category=raw.get("category"),
        raw_url=f"https://polymarket.com/event/{slug}" if slug else None,
    )


def sample_markets() -> List[Dict[str, Any]]:
    """Offline sample for demos when the local network cannot reach Polymarket."""
    return [
        {
            "id": "sample-fed-june",
            "question": "Will the Fed cut rates by June 2026?",
            "slug": "sample-fed-cut-rates-june-2026",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.34", "0.66"]',
            "volume24hr": 175000,
            "liquidityNum": 72000,
            "category": "Macro",
            "active": True,
            "closed": False,
            "archived": False,
        },
        {
            "id": "sample-election-turnout",
            "question": "Will US election turnout exceed the previous presidential cycle?",
            "slug": "sample-us-election-turnout",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.49", "0.51"]',
            "volume24hr": 98000,
            "liquidityNum": 54000,
            "category": "Politics",
            "active": True,
            "closed": False,
            "archived": False,
        },
    ]


def load_market_snapshots(
    limit: int = 8, enrich_clob: bool = True, sample_on_fail: bool = True
) -> List[MarketSnapshot]:
    try:
        raw_markets = get_active_markets(limit=limit)
    except Exception as exc:
        if not sample_on_fail:
            raise
        logger.warning("Using offline sample markets because Gamma API is unavailable: %s", exc)
        raw_markets = sample_markets()[:limit]
    snapshots = []
    for raw in raw_markets:
        try:
            snapshots.append(normalize_market(raw, enrich_clob=enrich_clob))
        except Exception as exc:
            logger.warning("Skipping malformed market: %s", exc)
    return snapshots


def snapshots_to_json(markets: Iterable[MarketSnapshot]) -> str:
    rows = []
    for market in markets:
        if hasattr(market, "model_dump"):
            rows.append(market.model_dump())
        else:
            rows.append(market.dict())
    return json.dumps(rows, indent=2)
