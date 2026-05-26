from __future__ import annotations

import hashlib
import json
import re
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

from risk import AnalysisSignal, MarketSnapshot, ResearchSummary

try:
    from crewai import Agent, Task
except Exception:  # pragma: no cover - optional runtime dependency
    Agent = None  # type: ignore[assignment]
    Task = None  # type: ignore[assignment]


def _bounded(value: float, low: float = 0.02, high: float = 0.98) -> float:
    return max(low, min(high, value))


def heuristic_research(market: MarketSnapshot, evidence: Optional[List[str]] = None) -> ResearchSummary:
    text = " ".join([market.question] + (evidence or [])).lower()
    bullish_terms = ["will", "approve", "win", "above", "higher", "record", "pass"]
    bearish_terms = ["not", "delay", "below", "lower", "fail", "reject", "lose"]
    bull = sum(1 for term in bullish_terms if re.search(rf"\b{re.escape(term)}\b", text))
    bear = sum(1 for term in bearish_terms if re.search(rf"\b{re.escape(term)}\b", text))
    if bull > bear:
        sentiment = "bullish_yes"
    elif bear > bull:
        sentiment = "bearish_yes"
    elif bull or bear:
        sentiment = "mixed"
    else:
        sentiment = "unknown"
    return ResearchSummary(
        market_id=market.id,
        question=market.question,
        evidence=evidence or [],
        sentiment=sentiment,
        confidence=0.45 if sentiment == "unknown" else 0.55,
    )


def local_analysis_signals(
    market: MarketSnapshot, research: Optional[ResearchSummary] = None
) -> List[AnalysisSignal]:
    base = market.yes_price if market.yes_price is not None else 0.5

    # Stable deterministic jitter prevents every market from getting identical
    # fallback analysis while keeping smoke tests reproducible.
    digest = hashlib.sha256(market.question.encode("utf-8")).hexdigest()
    jitter = (int(digest[:4], 16) / 65535.0 - 0.5) * 0.08
    sentiment_shift = 0.0
    if research and research.sentiment == "bullish_yes":
        sentiment_shift = 0.04
    elif research and research.sentiment == "bearish_yes":
        sentiment_shift = -0.04

    bull = _bounded(base + 0.07 + max(jitter, 0) + sentiment_shift)
    bear = _bounded(base - 0.06 + min(jitter, 0) + sentiment_shift)
    skeptic = _bounded((base * 0.75) + 0.125 + (sentiment_shift / 2.0))
    synthesized = _bounded(mean([bull, bear, skeptic]))

    return [
        AnalysisSignal(
            market_id=market.id,
            role="bull",
            true_probability=round(bull, 4),
            rationale="Bull case gives credit to favorable catalysts and underreaction.",
            confidence=0.55,
        ),
        AnalysisSignal(
            market_id=market.id,
            role="bear",
            true_probability=round(bear, 4),
            rationale="Bear case discounts crowded narratives and resolution ambiguity.",
            confidence=0.55,
        ),
        AnalysisSignal(
            market_id=market.id,
            role="skeptic",
            true_probability=round(skeptic, 4),
            rationale="Skeptic pulls toward base rate and penalizes weak evidence.",
            confidence=0.5,
        ),
        AnalysisSignal(
            market_id=market.id,
            role="synthesizer",
            true_probability=round(synthesized, 4),
            rationale="Average of bull, bear, and skeptic signals with no leverage.",
            confidence=0.58,
        ),
    ]


def create_bull_analyst(llm: Optional[Any] = None) -> Any:
    if Agent is None:
        return None
    return Agent(
        role="Bull Analyst",
        goal="Produce the strongest honest YES case and a calibrated probability.",
        backstory="You look for underpriced YES catalysts while staying numerical.",
        llm=llm,
        verbose=True,
    )


def create_bear_analyst(llm: Optional[Any] = None) -> Any:
    if Agent is None:
        return None
    return Agent(
        role="Bear Analyst",
        goal="Produce the strongest honest NO case and downside probability pressure.",
        backstory="You identify crowded trades, ambiguity, and hidden failure modes.",
        llm=llm,
        verbose=True,
    )


def create_skeptic_analyst(llm: Optional[Any] = None) -> Any:
    if Agent is None:
        return None
    return Agent(
        role="Skeptic Analyst",
        goal="Challenge evidence quality, market definitions, and overconfidence.",
        backstory="You are conservative and prefer no trade when evidence is thin.",
        llm=llm,
        verbose=True,
    )


def create_synthesizer(llm: Optional[Any] = None) -> Any:
    if Agent is None:
        return None
    return Agent(
        role="Synthesizer",
        goal="Combine data, research, and analyst views into strict Pydantic-compatible JSON probabilities.",
        backstory=(
            "You reconcile disagreements and output compact structured JSON only. "
            "Every signal must satisfy AnalysisSignal: market_id, role, "
            "true_probability between 0 and 1, rationale, confidence."
        ),
        llm=llm,
        verbose=True,
    )


def build_analysis_tasks(agents: Dict[str, Any]) -> List[Any]:
    if Task is None:
        return []

    return [
        Task(
            description=(
                "Given input JSON markets, validate prices/volume/liquidity. "
                "Return JSON summaries only matching the MarketSnapshot schema."
            ),
            expected_output="JSON list of market data summaries.",
            agent=agents["data"],
        ),
        Task(
            description=(
                "For each market, gather recent evidence and output compact JSON "
                "matching ResearchSummary: market_id, question, evidence, sentiment, confidence."
            ),
            expected_output="JSON research summaries only.",
            agent=agents["research"],
        ),
        Task(
            description=(
                "For each market, create bull, bear, skeptic, and synthesized "
                "true probabilities. Output strict JSON only. No markdown."
            ),
            expected_output=json.dumps(
                {
                    "market_id": "string",
                    "signals": [
                        {
                            "role": "bull|bear|skeptic|synthesizer",
                            "true_probability": 0.57,
                            "confidence": 0.6,
                            "rationale": "short text",
                        }
                    ],
                }
            ),
            agent=agents["synthesizer"],
        ),
    ]


def signal_payload(signals: Iterable[AnalysisSignal]) -> List[Dict[str, Any]]:
    payload = []
    for signal in signals:
        payload.append(signal.model_dump() if hasattr(signal, "model_dump") else signal.dict())
    return payload
