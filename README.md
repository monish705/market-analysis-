# Polymarket Pyramid Edge Scanner

Repository name: `polymarket-pyramid-edge-scanner`

Paper-mode hierarchical multi-agent scanner for finding prediction-market edge candidates on Polymarket.

The system scans active markets, enriches prices from the CLOB, synthesizes a local or CrewAI-backed probability estimate, applies liquidity/Kelly risk filters, and emits strict JSON trade decisions.

This is research software, not financial advice. It does not place orders.

## File Structure

```text
project/
|-- main.py
|-- e2e_test.py
|-- agents/
|   |-- __init__.py
|   |-- data_agents.py
|   |-- analyst_agents.py
|   `-- risk_agent.py
|-- tools/
|   |-- __init__.py
|   |-- polymarket.py
|   `-- search.py
|-- config.py
|-- risk.py
|-- backtester.py
|-- requirements.txt
|-- README.md
`-- .env.example
```

## Setup

```bash
cd project
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set `CEREBRAS_API_KEY` in `.env` for CrewAI hierarchical mode. Keep `.env` out of git.

Example `.env`:

```text
CEREBRAS_API_KEY=your_cerebras_key_here
CEREBRAS_MODEL=llama3.1-70b
CEREBRAS_BASE_URL=https://api.cerebras.ai/v1
```

## Run

Live Polymarket scan in local deterministic paper mode:

```bash
python main.py --scan --limit 8 --backtest
```

Full live E2E validation:

```bash
python main.py --e2e
```

The latest published test evidence is in [TEST_RESULTS.md](TEST_RESULTS.md).

Direct E2E script:

```bash
python e2e_test.py
```

CrewAI hierarchical mode with Cerebras:

```bash
python main.py --scan --limit 8 --use-crewai
```

The CrewAI path requires `crewai` plus a valid Cerebras key. The local paper-mode path works without an LLM key.

## Data Pulling

The Polymarket adapter now prefers:

```text
https://gamma-api.polymarket.com/events?active=true&closed=false&limit=10&order=volume_24hr&ascending=false
```

It falls back to:

```text
https://gamma-api.polymarket.com/markets?active=true&closed=false
```

For each market, it parses `clobTokenIds` and enriches YES probability from:

```text
https://clob.polymarket.com/midpoint?token_id=YES_TOKEN_ID
```

Filtering:

- `volume_24hr > 20000`
- market is active/open/unarchived
- liquidity is nonzero or CLOB token IDs are present

## Robustness

Requests use a `requests.Session`, 10 second timeout, 3 attempts, and 1-3 second backoff. If local DNS routes `gamma-api.polymarket.com` or `clob.polymarket.com` to a bad ISP edge, the client falls back to Cloudflare public IPs while preserving HTTPS hostnames.

Relevant `.env` knobs:

```text
HTTP_TIMEOUT_SECONDS=10
POLYMARKET_MAX_ATTEMPTS=3
POLYMARKET_PUBLIC_DNS_FALLBACK=true
POLYMARKET_PUBLIC_IPS=104.18.34.205,172.64.153.51
```

If timeouts persist, try a VPN/proxy, change DNS to 1.1.1.1, or set `POLYMARKET_PUBLIC_DNS_FALLBACK=true`.

## Risk Rules

- YES edge = synthesized true probability - market YES price.
- Trade only when `edge > 0.08`.
- Liquidity/volume threshold is 20k.
- Size via fractional Kelly with a 2 percent portfolio cap.
- Output is a strict Pydantic `TradeDecision`.

## Security

No API keys are committed. `.env` is ignored, and `.env.example` contains placeholders only.

## Backtester

Mock deterministic P&L simulation:

```bash
python backtester.py data/latest_scan.json --bankroll 10000
```

Replace `deterministic_resolution` with real resolved market outcomes for historical testing.

## Extending to Kalshi

Add a `tools/kalshi.py` adapter that normalizes Kalshi events into the same `MarketSnapshot` schema:

- `question`
- `yes_price`
- `volume`
- `liquidity`
- `end_date`
- venue-specific IDs

Then reuse the analyst and risk pipeline unchanged.
