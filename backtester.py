from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, List

from pydantic import BaseModel

from risk import TradeDecision


class BacktestResult(BaseModel):
    trades: int
    wins: int
    losses: int
    pnl_usd: float
    ending_bankroll_usd: float
    roi_percent: float


@dataclass
class MockResolution:
    market_id: str
    resolved_yes: bool


def deterministic_resolution(market_id: str, true_probability: float) -> MockResolution:
    digest = hashlib.sha256(market_id.encode("utf-8")).hexdigest()
    draw = int(digest[:8], 16) / 0xFFFFFFFF
    return MockResolution(market_id=market_id, resolved_yes=draw < true_probability)


def simulate_pnl(
    decisions: Iterable[TradeDecision],
    starting_bankroll_usd: float = 10000.0,
) -> BacktestResult:
    bankroll = starting_bankroll_usd
    wins = 0
    losses = 0
    trades = 0

    for decision in decisions:
        if not decision.decision.startswith("BUY_YES"):
            continue
        if decision.market_probability <= 0:
            continue
        trades += 1
        stake = decision.recommended_position_usd
        shares = stake / decision.market_probability
        resolution = deterministic_resolution(
            decision.market_id, decision.true_probability
        )
        if resolution.resolved_yes:
            pnl = shares - stake
            wins += 1
        else:
            pnl = -stake
            losses += 1
        bankroll += pnl

    pnl_total = bankroll - starting_bankroll_usd
    roi = (pnl_total / starting_bankroll_usd) * 100 if starting_bankroll_usd else 0.0
    return BacktestResult(
        trades=trades,
        wins=wins,
        losses=losses,
        pnl_usd=round(pnl_total, 2),
        ending_bankroll_usd=round(bankroll, 2),
        roi_percent=round(roi, 2),
    )


def load_decisions(path: str) -> List[TradeDecision]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = payload["decisions"] if isinstance(payload, dict) else payload
    return [TradeDecision(**row) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock backtest pyramid decisions.")
    parser.add_argument("decisions_json", help="Path to JSON decisions from main.py")
    parser.add_argument("--bankroll", type=float, default=10000.0)
    args = parser.parse_args()
    result = simulate_pnl(load_decisions(args.decisions_json), args.bankroll)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

