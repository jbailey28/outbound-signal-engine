"""Account opportunity scoring (Milestone 4).

Turns the affiliate signal from M2 into a prioritization score, following the
rule that the *least-penetrated* accounts are the best targets:

    greenfield (no program)         -> highest  (untapped channel = most upside)
    on a non-Impact platform        -> high     (switchable: competitor or in-house)
    on Impact already               -> lowest   (hardest to sell into)
    unknown (signal unresolved)     -> middle, flagged for manual review

The numbers live in SEGMENT_SCORES so they're easy to tune. trigger_score is a
placeholder for M3 (recent news/funding/hiring) that will add a timing bonus on
top of this fit score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Our own platform — accounts already here are the lowest-opportunity targets.
HOME_PLATFORM = "impact"

SEGMENT_SCORES: dict[str, int] = {
    "greenfield": 100,
    "non_impact_platform": 70,
    "unknown": 50,
    "on_impact": 20,
}


@dataclass
class Score:
    account_id: str | None
    account_name: str
    segment: str
    fit_score: int
    trigger_score: int = 0
    needs_review: bool = False
    reasons: dict[str, Any] = field(default_factory=dict)

    @property
    def total_score(self) -> int:
        return self.fit_score + self.trigger_score


def classify_segment(has_program: bool | None, platform: str | None) -> str:
    """Map an affiliate signal to an opportunity segment."""
    if has_program is None:
        return "unknown"
    if has_program is False:
        return "greenfield"
    # has a program
    if (platform or "").lower() == HOME_PLATFORM:
        return "on_impact"
    return "non_impact_platform"


def score_account(
    *,
    account_id: str | None,
    account_name: str,
    has_program: bool | None,
    platform: str | None,
    trigger_score: int = 0,
) -> Score:
    """Compute the opportunity score for one account from its signal."""
    segment = classify_segment(has_program, platform)
    fit = SEGMENT_SCORES[segment]
    reasons = {
        "segment": segment,
        "has_program": has_program,
        "platform": platform,
        "fit_basis": f"{segment} -> {fit}",
    }
    return Score(
        account_id=account_id,
        account_name=account_name,
        segment=segment,
        fit_score=fit,
        trigger_score=trigger_score,
        needs_review=(segment == "unknown"),
        reasons=reasons,
    )
