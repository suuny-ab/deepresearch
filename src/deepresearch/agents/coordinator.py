"""Coordinator: merge evidence cards from subquestion agents and detect conflicts.

The coordinator runs after all subquestion agents complete.  It:
1. Merges evidence cards (deduplicating by id)
2. Detects cross-subquestion corroboration — when agents working on different
   subquestions independently find the same fact from different domains
3. Detects contradictions — when different agents report conflicting findings
   on the same topic
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from deepresearch.state import EvidenceCard
from deepresearch.utils.urls import extract_domain


@dataclass
class Contradiction:
    """Two claims from different subquestions that appear to conflict."""
    topic: str
    claim_a: str
    agent_a: str
    source_a: str
    claim_b: str
    agent_b: str
    source_b: str
    explanation: str = ""


@dataclass
class CoordinatorResult:
    """Merged evidence with cross-agent findings."""
    evidence_cards: list[EvidenceCard] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    cross_agent_corroborations: int = 0


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------

def _merge_cards(agent_results) -> list[EvidenceCard]:
    """Merge evidence cards from all agents, deduplicating by id."""
    seen: set[str] = set()
    merged: list[EvidenceCard] = []
    for result in agent_results:
        for card in result.evidence_cards:
            if card.id not in seen:
                seen.add(card.id)
                merged.append(card)
    return merged


# ---------------------------------------------------------------------------
# Cross-agent corroboration
# ---------------------------------------------------------------------------

def _normalize_claim_text(text: str) -> str:
    """Normalize claim text for fuzzy comparison."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _claims_overlap(claim_a: str, claim_b: str, threshold: float = 0.5) -> bool:
    """Check if two claims likely refer to the same fact using word overlap."""
    words_a = set(_normalize_claim_text(claim_a).split())
    words_b = set(_normalize_claim_text(claim_b).split())
    if not words_a or not words_b:
        return False
    intersection = words_a & words_b
    smaller = min(len(words_a), len(words_b))
    return len(intersection) / smaller >= threshold


def _detect_cross_agent_corroboration(
    agent_results,
) -> tuple[list[EvidenceCard], int]:
    """Find claims from different agents that independently corroborate each other.

    When two agents working on different subquestions find the same fact from
    different domain sources, this is strong evidence of truth.  We upgrade
    the corroboration level of matching claims.
    """
    # Group cards by agent
    agent_cards: dict[str, list[EvidenceCard]] = defaultdict(list)
    for result in agent_results:
        for card in result.evidence_cards:
            agent_cards[result.subquestion_id].append(card)

    agent_ids = list(agent_cards.keys())
    cross_count = 0

    for i in range(len(agent_ids)):
        for j in range(i + 1, len(agent_ids)):
            agent_a, agent_b = agent_ids[i], agent_ids[j]
            for card_a in agent_cards[agent_a]:
                domain_a = extract_domain(card_a.source_url)
                for card_b in agent_cards[agent_b]:
                    domain_b = extract_domain(card_b.source_url)
                    # Must be different domains for independent corroboration
                    if domain_a == domain_b:
                        continue
                    if _claims_overlap(card_a.claim, card_b.claim):
                        # Upgrade card_a if it has fewer corroborating sources
                        if card_b.source_url not in card_a.corroborating_sources:
                            card_a.corroborating_sources.append(card_b.source_url)
                            if card_a.corroboration_level == "single_source":
                                card_a.corroboration_level = "weakly_corroborated"
                            elif card_a.corroboration_level == "weakly_corroborated":
                                card_a.corroboration_level = "strongly_corroborated"
                        # Reciprocal
                        if card_a.source_url not in card_b.corroborating_sources:
                            card_b.corroborating_sources.append(card_a.source_url)
                            if card_b.corroboration_level == "single_source":
                                card_b.corroboration_level = "weakly_corroborated"
                            elif card_b.corroboration_level == "weakly_corroborated":
                                card_b.corroboration_level = "strongly_corroborated"
                        cross_count += 1

    # Return all cards (now with upgraded corroboration)
    all_cards = _merge_cards(agent_results)
    return all_cards, cross_count


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------

_CONTRADICTION_MARKERS = [
    # English
    r"\b(however|but|although|on the other hand|in contrast|conversely|whereas|while)\b",
    # Chinese
    r"(然而|但是|不过|另一方面|相反|与之相对|相比之下)",
]


def _has_contradiction_markers(text: str) -> bool:
    """Quick check: does the claim text contain contradiction signals?"""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _CONTRADICTION_MARKERS)


def _detect_contradictions(agent_results) -> list[Contradiction]:
    """Detect claims from different agents that present opposing viewpoints.

    Strategy: when two claims from different agents share significant word
    overlap but contain contradiction markers (however/but/although etc.),
    flag them as potential contradictions for the writer to address.
    """
    contradictions: list[Contradiction] = []

    agent_cards: dict[str, list[EvidenceCard]] = defaultdict(list)
    for result in agent_results:
        for card in result.evidence_cards:
            agent_cards[result.subquestion_id].append(card)

    agent_ids = list(agent_cards.keys())
    for i in range(len(agent_ids)):
        for j in range(i + 1, len(agent_ids)):
            agent_a, agent_b = agent_ids[i], agent_ids[j]
            for card_a in agent_cards[agent_a]:
                for card_b in agent_cards[agent_b]:
                    if not _claims_overlap(card_a.claim, card_b.claim, threshold=0.3):
                        continue
                    # Check if either contains contradiction markers
                    if _has_contradiction_markers(card_a.claim) or _has_contradiction_markers(card_b.claim):
                        contradictions.append(Contradiction(
                            topic=_extract_topic(card_a.claim, card_b.claim),
                            claim_a=card_a.claim,
                            agent_a=agent_a,
                            source_a=card_a.source_url,
                            claim_b=card_b.claim,
                            agent_b=agent_b,
                            source_b=card_b.source_url,
                            explanation=(
                                f"Agent '{agent_a}' and '{agent_b}' present different perspectives "
                                f"on the same topic from independent sources."
                            ),
                        ))

    return contradictions


def _extract_topic(claim_a: str, claim_b: str) -> str:
    """Extract a short topic label from overlapping claim words."""
    words_a = set(_normalize_claim_text(claim_a).split())
    words_b = set(_normalize_claim_text(claim_b).split())
    common = words_a & words_b
    # Remove stop words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "under", "and", "but",
        "or", "not", "no", "if", "then", "than", "that", "this", "these",
        "those", "it", "its", "的", "了", "在", "是", "有", "和", "与", "不",
        "也", "就", "都", "而", "及", "到", "着", "被", "从",
    }
    meaningful = common - stop_words
    topic_words = sorted(meaningful)[:5]
    return " ".join(topic_words) if topic_words else "unknown topic"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def coordinate(agent_results) -> CoordinatorResult:
    """Run coordination: merge cards, detect cross-agent corroboration and contradictions.

    Parameters
    ----------
    agent_results:
        List of :class:`AgentResult` from :func:`~subquestion_agent.run_subquestion_agent`.

    Returns
    -------
    CoordinatorResult
        Merged evidence cards with cross-agent findings.
    """
    if not agent_results:
        return CoordinatorResult()

    # Merge cards with cross-agent corroboration
    merged_cards, cross_count = _detect_cross_agent_corroboration(agent_results)

    # Detect contradictions
    contradictions = _detect_contradictions(agent_results)

    return CoordinatorResult(
        evidence_cards=merged_cards,
        contradictions=contradictions,
        cross_agent_corroborations=cross_count,
    )
