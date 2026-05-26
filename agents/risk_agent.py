from __future__ import annotations

from statistics import mean
from typing import Any, Iterable, List, Optional

from risk import AnalysisSignal, MarketSnapshot, TradeDecision, assess_risk, decision_from_risk

try:
    from crewai import Agent, Task
except Exception:  # pragma: no cover - optional runtime dependency
    Agent = None  # type: ignore[assignment]
    Task = None  # type: ignore[assignment]


CENTRAL_DECIDER_PROMPT = """
You are final risk-aware boss. Input: JSON summaries only.
Market says X%, Our synth Y% -> Edge Z%.
Rules: edge>0.08, liq>20k, size via kelly capped.
Paper mode only. Never place orders.
Output strict JSON matching TradeDecision:
{"market_id": "string", "question": "string", "decision": "BUY_YES_150USD", "edge": 0.12, "edge_percent": 12, "market_probability": 0.42, "true_probability": 0.54, "recommended_position_usd": 150, "rationale": "short", "confidence": 0.75}
"""


def create_risk_assessor(llm: Optional[Any] = None) -> Any:
    if Agent is None:
        return None
    return Agent(
        role="Risk Assessor",
        goal="Apply liquidity, edge, Kelly sizing, and position cap filters.",
        backstory="You reject trades that fail the rules even if the story is exciting.",
        llm=llm,
        verbose=True,
    )


def create_central_decider(llm: Optional[Any] = None) -> Any:
    if Agent is None:
        return None
    return Agent(
        role="Central Decider",
        goal="Make final paper-mode risk-aware trading decisions from JSON summaries only.",
        backstory=CENTRAL_DECIDER_PROMPT,
        llm=llm,
        verbose=True,
    )


def build_decision_task(decider: Any) -> List[Any]:
    if Task is None:
        return []
    return [
        Task(
            description=(
                CENTRAL_DECIDER_PROMPT
                + "\nReview synthesized probabilities and risk assessments. "
                + "Return only valid JSON decisions."
            ),
            expected_output='JSON: {"decisions": [{"decision": "NO_TRADE", "edge": 0, "rationale": "...", "confidence": 0.5}]}',
            agent=decider,
        )
    ]


def decide_locally(
    market: MarketSnapshot,
    signals: Iterable[AnalysisSignal],
    bankroll_usd: float,
) -> TradeDecision:
    signal_list = list(signals)
    synth = next((s for s in signal_list if s.role == "synthesizer"), None)
    if synth:
        true_prob = synth.true_probability
        confidence = synth.confidence
        rationale = synth.rationale
    else:
        true_prob = mean([signal.true_probability for signal in signal_list])
        confidence = mean([signal.confidence for signal in signal_list])
        rationale = "Mean of available analyst probabilities."

    assessment = assess_risk(market, true_prob, bankroll_usd=bankroll_usd)
    return decision_from_risk(market, assessment, confidence=confidence, rationale=rationale)
