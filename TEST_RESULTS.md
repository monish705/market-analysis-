# Live Test Results

Tested from `C:\Users\brind\Documents\New project\project` on May 26, 2026.

## Commands Run

```powershell
python main.py --e2e
python -m pytest tests/ -q
python main.py --scan --limit 5 --backtest --out data/latest_live_scan.json
```

## E2E Result

```text
E2E Passed: 5 markets, 2+ decisions, no timeouts
market_count: 5
decision_count: 3
mock_backtest:
  trades: 0
  wins: 0
  losses: 0
  pnl_usd: 0.0
  ending_bankroll_usd: 10000.0
```

## Pytest Result

```text
.                                                                        [100%]
1 passed in 11.26s
```

## Live Market Evidence

These markets were fetched live through the Polymarket Gamma `/events` endpoint and enriched with CLOB YES midpoint prices.

```text
LIVE_MARKET_COUNT 5

1. id=824952
   yes=0.73
   vol24h=56819.12
   liq=34299.78
   question=MicroStrategy sells any Bitcoin by December 31, 2026?

2. id=692258
   yes=0.3175
   vol24h=116572.52
   liq=60500.09
   question=MicroStrategy sells any Bitcoin by June 30, 2026?

3. id=2169995
   yes=0.0295
   vol24h=462827.84
   liq=114503.93
   question=MicroStrategy sells any Bitcoin by May 31, 2026?

4. id=597967
   yes=0.235
   vol24h=66868.89
   liq=95764.99
   question=Starmer out by June 30, 2026?

5. id=666655
   yes=0.715
   vol24h=28581.46
   liq=78068.33
   question=Starmer out by December 31, 2026?
```

## Decision Evidence

From `data/latest_live_scan.json`:

```text
SCAN_MODE local_heuristic
DECISIONS 5
TRACES 5

824952 market=0.725  synth=0.7006 edge=-0.0244 decision=NO_TRADE
692258 market=0.3135 synth=0.3456 edge=0.0321  decision=NO_TRADE
2169995 market=0.0295 synth=0.1021 edge=0.0726 decision=NO_TRADE
597967 market=0.235  synth=0.2496 edge=0.0146  decision=NO_TRADE
666655 market=0.715  synth=0.7088 edge=-0.0062 decision=NO_TRADE
```

All decisions were `NO_TRADE` because none cleared the configured `edge > 0.08` filter.

