from __future__ import annotations

import json
from typing import Any, Dict, List

from backtester import simulate_pnl
from main import run_pyramid
from risk import TradeDecision
from tools.polymarket import load_market_snapshots


def run_e2e() -> Dict[str, Any]:
    markets = load_market_snapshots(limit=5, enrich_clob=True, sample_on_fail=False)
    if len(markets) < 5:
        raise AssertionError(f"Expected 5 real markets, got {len(markets)}")

    result = run_pyramid(
        limit=3,
        use_crewai=False,
        enrich_clob=True,
        sample_on_fail=False,
    )
    decisions: List[TradeDecision] = [
        TradeDecision(**row) for row in result.get("decisions", [])
    ]
    if len(decisions) < 2:
        raise AssertionError(f"Expected 2+ decisions, got {len(decisions)}")

    for decision in decisions:
        expected_edge = round(
            decision.true_probability - decision.market_probability, 4
        )
        if decision.edge != expected_edge:
            raise AssertionError(
                f"Edge mismatch for {decision.market_id}: "
                f"{decision.edge} != {expected_edge}"
            )

    traces = result.get("traces", [])
    if not traces:
        raise AssertionError("Missing bottom/middle trace output")
    for trace in traces:
        if "market" not in trace or "signals" not in trace:
            raise AssertionError("Trace missing market or signals handoff")
        if not any(signal["role"] == "synthesizer" for signal in trace["signals"]):
            raise AssertionError("Trace missing synthesized middle-layer signal")

    backtest = simulate_pnl(decisions)
    payload = {
        "status": "E2E Passed: 5 markets, 2+ decisions, no timeouts",
        "market_count": len(markets),
        "decision_count": len(decisions),
        "decisions": [
            decision.model_dump()
            if hasattr(decision, "model_dump")
            else decision.dict()
            for decision in decisions
        ],
        "mock_backtest": backtest.model_dump()
        if hasattr(backtest, "model_dump")
        else backtest.dict(),
    }
    return payload


def test_e2e_live_data() -> None:
    payload = run_e2e()
    assert payload["market_count"] >= 5
    assert payload["decision_count"] >= 2


if __name__ == "__main__":
    print(json.dumps(run_e2e(), indent=2))
