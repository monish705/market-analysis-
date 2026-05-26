from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from config import (
    DEFAULT_BANKROLL_USD,
    KELLY_FRACTION,
    MAX_POSITION_FRACTION,
    MIN_EDGE,
    MIN_VOLUME_USD,
)


def asdict(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


class MarketSnapshot(BaseModel):
    id: str
    question: str
    slug: Optional[str] = None
    condition_id: Optional[str] = None
    yes_token_id: Optional[str] = None
    no_token_id: Optional[str] = None
    yes_price: Optional[float] = None
    no_price: Optional[float] = None
    volume: float = 0.0
    liquidity: float = 0.0
    end_date: Optional[str] = None
    category: Optional[str] = None
    raw_url: Optional[str] = None


class ResearchSummary(BaseModel):
    market_id: str
    question: str
    evidence: List[str] = Field(default_factory=list)
    sentiment: Literal["bullish_yes", "bearish_yes", "mixed", "unknown"] = "unknown"
    confidence: float = Field(default=0.5, ge=0, le=1)


class AnalysisSignal(BaseModel):
    market_id: str
    role: Literal["bull", "bear", "skeptic", "synthesizer"]
    true_probability: float = Field(ge=0, le=1)
    rationale: str
    confidence: float = Field(default=0.5, ge=0, le=1)


class RiskAssessment(BaseModel):
    market_id: str
    market_probability: float = Field(ge=0, le=1)
    true_probability: float = Field(ge=0, le=1)
    edge: float
    edge_percent: float
    expected_value_per_share: float
    liquidity_ok: bool
    volume: float
    kelly_fraction: float
    recommended_position_usd: float
    cap_usd: float
    passed: bool
    reasons: List[str] = Field(default_factory=list)


class TradeDecision(BaseModel):
    market_id: str
    question: str
    decision: str
    edge: float
    edge_percent: float
    market_probability: float
    true_probability: float
    recommended_position_usd: float
    confidence: float = Field(ge=0, le=1)
    rationale: str


def implied_decimal_odds(price: float) -> float:
    if price <= 0:
        return 0.0
    return 1.0 / price


def fractional_kelly(
    edge: float,
    prob: float,
    bankroll_usd: float = DEFAULT_BANKROLL_USD,
    fraction: float = KELLY_FRACTION,
    cap_fraction: float = MAX_POSITION_FRACTION,
) -> float:
    """Return capped fractional Kelly stake in USD for a binary YES share."""
    market_probability = prob - edge
    true_probability = prob
    if edge <= 0 or market_probability <= 0 or market_probability >= 1:
        return 0.0
    b = implied_decimal_odds(market_probability) - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - true_probability
    full_kelly = ((b * true_probability) - q) / b
    fractional = max(0.0, full_kelly * fraction)
    capped = min(fractional, cap_fraction)
    return round(capped * bankroll_usd, 2)


def kelly_size(edge: float, prob: float, bankroll_usd: float = 1000.0) -> float:
    """Simple cap example matching the requested prototype snippet."""
    _ = prob
    return max(0.0, edge / 1.5) * bankroll_usd


def assess_risk(
    market: MarketSnapshot,
    true_probability: float,
    bankroll_usd: float = DEFAULT_BANKROLL_USD,
    min_edge: float = MIN_EDGE,
    min_volume: float = MIN_VOLUME_USD,
    max_position_fraction: float = MAX_POSITION_FRACTION,
) -> RiskAssessment:
    market_probability = market.yes_price if market.yes_price is not None else 0.5
    edge = true_probability - market_probability
    cap_usd = round(bankroll_usd * max_position_fraction, 2)
    size_usd = fractional_kelly(
        edge=edge,
        prob=true_probability,
        bankroll_usd=bankroll_usd,
        cap_fraction=max_position_fraction,
    )
    size_usd = min(size_usd, cap_usd)
    liquidity_ok = market.volume >= min_volume or market.liquidity >= min_volume

    reasons: List[str] = []
    if edge < min_edge:
        reasons.append(f"edge below threshold: {edge:.2%} < {min_edge:.2%}")
    if not liquidity_ok:
        reasons.append(
            f"liquidity/volume below threshold: volume={market.volume:.0f}, "
            f"liquidity={market.liquidity:.0f}, required={min_volume:.0f}"
        )
    if size_usd <= 0:
        reasons.append("Kelly size is zero after caps")

    return RiskAssessment(
        market_id=market.id,
        market_probability=round(market_probability, 4),
        true_probability=round(true_probability, 4),
        edge=round(edge, 4),
        edge_percent=round(edge * 100, 2),
        expected_value_per_share=round(edge, 4),
        liquidity_ok=liquidity_ok,
        volume=market.volume,
        kelly_fraction=round(size_usd / bankroll_usd, 4) if bankroll_usd else 0.0,
        recommended_position_usd=round(size_usd, 2),
        cap_usd=cap_usd,
        passed=edge >= min_edge and liquidity_ok and size_usd > 0,
        reasons=reasons,
    )


def decision_from_risk(
    market: MarketSnapshot,
    assessment: RiskAssessment,
    confidence: float,
    rationale: str,
) -> TradeDecision:
    if assessment.passed:
        size = int(round(assessment.recommended_position_usd / 10.0) * 10)
        decision = f"BUY_YES_{size}USD"
    else:
        decision = "NO_TRADE"

    return TradeDecision(
        market_id=market.id,
        question=market.question,
        decision=decision,
        edge=assessment.edge,
        edge_percent=assessment.edge_percent,
        market_probability=assessment.market_probability,
        true_probability=assessment.true_probability,
        recommended_position_usd=assessment.recommended_position_usd
        if assessment.passed
        else 0.0,
        confidence=round(confidence, 2),
        rationale=rationale if assessment.passed else "; ".join(assessment.reasons),
    )
