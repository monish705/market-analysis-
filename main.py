from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agents.analyst_agents import (
    build_analysis_tasks,
    create_bear_analyst,
    create_bull_analyst,
    create_skeptic_analyst,
    create_synthesizer,
    heuristic_research,
    local_analysis_signals,
    signal_payload,
)
from agents.data_agents import (
    create_data_agent,
    create_external_research_agent,
    create_historical_agent,
)
from agents.risk_agent import (
    build_decision_task,
    create_central_decider,
    create_risk_assessor,
    decide_locally,
)
from backtester import simulate_pnl
from config import (
    CEREBRAS_BASE_URL,
    CEREBRAS_KEY,
    CEREBRAS_MODEL,
    DATA_DIR,
    DB_PATH,
    DEFAULT_BANKROLL_USD,
)
from risk import TradeDecision
from tools.polymarket import load_market_snapshots

try:
    from crewai import Crew, LLM, Process
except Exception:  # pragma: no cover - optional runtime dependency
    Crew = None  # type: ignore[assignment]
    LLM = None  # type: ignore[assignment]
    Process = None  # type: ignore[assignment]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pyramid")


def build_cerebras_llm() -> Any:
    if LLM is None:
        return None
    if not CEREBRAS_KEY:
        return None
    return LLM(
        model=CEREBRAS_MODEL,
        api_key=CEREBRAS_KEY,
        base_url=CEREBRAS_BASE_URL,
        temperature=0.2,
        max_tokens=4096,
    )


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                market_id TEXT NOT NULL,
                question TEXT NOT NULL,
                decision_json TEXT NOT NULL
            )
            """
        )


def persist_decisions(decisions: List[TradeDecision]) -> None:
    init_db()
    created_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        for decision in decisions:
            payload = (
                decision.model_dump()
                if hasattr(decision, "model_dump")
                else decision.dict()
            )
            conn.execute(
                """
                INSERT INTO scans (created_at, market_id, question, decision_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    created_at,
                    decision.market_id,
                    decision.question,
                    json.dumps(payload),
                ),
            )


def run_local_pyramid(
    limit: int, bankroll_usd: float, enrich_clob: bool, sample_on_fail: bool = True
) -> Dict[str, Any]:
    logger.info("Fetching active Polymarket markets")
    markets = load_market_snapshots(
        limit=limit, enrich_clob=enrich_clob, sample_on_fail=sample_on_fail
    )
    decisions: List[TradeDecision] = []
    traces: List[Dict[str, Any]] = []

    for market in markets:
        research = heuristic_research(market)
        signals = local_analysis_signals(market, research=research)
        decision = decide_locally(market, signals, bankroll_usd=bankroll_usd)
        decisions.append(decision)
        traces.append(
            {
                "market": market.model_dump()
                if hasattr(market, "model_dump")
                else market.dict(),
                "research": research.model_dump()
                if hasattr(research, "model_dump")
                else research.dict(),
                "signals": signal_payload(signals),
            }
        )

    persist_decisions(decisions)
    return {
        "mode": "local_heuristic",
        "decisions": [
            decision.model_dump() if hasattr(decision, "model_dump") else decision.dict()
            for decision in decisions
        ],
        "traces": traces,
    }


def run_crewai_pyramid(
    limit: int, bankroll_usd: float, enrich_clob: bool, sample_on_fail: bool = True
) -> Dict[str, Any]:
    llm = build_cerebras_llm()
    if Crew is None or Process is None or llm is None:
        logger.warning("CrewAI/Cerebras unavailable; falling back to local heuristic mode")
        return run_local_pyramid(
            limit=limit,
            bankroll_usd=bankroll_usd,
            enrich_clob=enrich_clob,
            sample_on_fail=sample_on_fail,
        )

    markets = load_market_snapshots(
        limit=limit, enrich_clob=enrich_clob, sample_on_fail=sample_on_fail
    )
    agents = {
        "data": create_data_agent(llm),
        "research": create_external_research_agent(llm),
        "historical": create_historical_agent(llm),
        "bull": create_bull_analyst(llm),
        "bear": create_bear_analyst(llm),
        "skeptic": create_skeptic_analyst(llm),
        "risk": create_risk_assessor(llm),
        "synthesizer": create_synthesizer(llm),
        "decider": create_central_decider(llm),
    }
    crew_agents = [agent for agent in agents.values() if agent is not None]
    tasks = build_analysis_tasks(agents) + build_decision_task(agents["decider"])
    crew = Crew(
        agents=crew_agents,
        tasks=tasks,
        process=Process.hierarchical,
        manager_llm=llm,
        verbose=True,
    )
    result = crew.kickoff(
        inputs={
            "markets": [
                market.model_dump() if hasattr(market, "model_dump") else market.dict()
                for market in markets
            ],
            "bankroll_usd": bankroll_usd,
        }
    )
    return {
        "mode": "crewai_hierarchical",
        "raw_result": str(result),
    }


def run_pyramid(
    limit: int = 8,
    bankroll_usd: float = DEFAULT_BANKROLL_USD,
    use_crewai: bool = False,
    enrich_clob: bool = True,
    sample_on_fail: bool = True,
) -> Dict[str, Any]:
    if use_crewai:
        return run_crewai_pyramid(
            limit=limit,
            bankroll_usd=bankroll_usd,
            enrich_clob=enrich_clob,
            sample_on_fail=sample_on_fail,
        )
    return run_local_pyramid(
        limit=limit,
        bankroll_usd=bankroll_usd,
        enrich_clob=enrich_clob,
        sample_on_fail=sample_on_fail,
    )


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hierarchical multi-agent LLM pyramid for Polymarket inefficiency scans."
    )
    parser.add_argument("--scan", action="store_true", help="Run a live market scan")
    parser.add_argument("--limit", type=int, default=8, help="Number of markets to scan")
    parser.add_argument("--bankroll", type=float, default=DEFAULT_BANKROLL_USD)
    parser.add_argument("--use-crewai", action="store_true", help="Use CrewAI+Cerebras")
    parser.add_argument("--no-clob", action="store_true", help="Use Gamma prices only")
    parser.add_argument(
        "--sample-on-fail",
        action="store_true",
        help="Use built-in sample markets if Polymarket is unreachable",
    )
    parser.add_argument("--backtest", action="store_true", help="Run mock P&L sim on decisions")
    parser.add_argument("--e2e", action="store_true", help="Run live data E2E validation")
    parser.add_argument("--out", type=Path, default=DATA_DIR / "latest_scan.json")
    args = parser.parse_args()

    if args.e2e:
        from e2e_test import run_e2e

        payload = run_e2e()
        print(json.dumps(payload, indent=2))
        return

    if not args.scan:
        parser.print_help()
        return

    result = run_pyramid(
        limit=args.limit,
        bankroll_usd=args.bankroll,
        use_crewai=args.use_crewai,
        enrich_clob=not args.no_clob,
        sample_on_fail=args.sample_on_fail,
    )

    if args.backtest and "decisions" in result:
        decisions = [TradeDecision(**row) for row in result["decisions"]]
        backtest = simulate_pnl(decisions, starting_bankroll_usd=args.bankroll)
        result["mock_backtest"] = (
            backtest.model_dump() if hasattr(backtest, "model_dump") else backtest.dict()
        )

    write_json(args.out, result)
    print(json.dumps(result, indent=2))
    logger.info("Wrote scan to %s", args.out)


if __name__ == "__main__":
    main()
