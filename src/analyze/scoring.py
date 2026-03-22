"""
VERIFY V2 — Scoring Engine
=============================
Usefulness and novelty scoring for accepted assertions.
"""

import re
from typing import List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import AssertionStatus, CandidateAssertion, IntentType


class ScoringEngine:
    """Score assertions for usefulness and novelty."""

    def usefulness(
        self,
        assertion_text: str,
        intent: IntentType,
        status: AssertionStatus,
    ) -> float:
        """Heuristic usefulness score in [0, 1]."""
        score = 0.5

        # Proven assertions are more useful
        if status == AssertionStatus.PROVEN_FORMAL:
            score += 0.15
        elif status == AssertionStatus.SYNTAX_OK_ONLY:
            score += 0.05

        # Intent weighting
        intent_bonus = {
            IntentType.SAFETY: 0.20,
            IntentType.LIVENESS: 0.15,
            IntentType.TIMING: 0.10,
            IntentType.RESET: 0.05,
            IntentType.INVARIANT: 0.0,
        }
        score += intent_bonus.get(intent, 0.0)

        # Complexity bonus
        if "|->" in assertion_text or "|=>" in assertion_text:
            score += 0.05
        if "$past(" in assertion_text or "$rose(" in assertion_text:
            score += 0.05
        if "##" in assertion_text:
            score += 0.05

        # Penalty for width-only assertions
        if re.search(r"\$bits\(|width|size", assertion_text, re.IGNORECASE):
            score -= 0.20

        return min(1.0, max(0.0, score))

    def novelty(
        self,
        candidate: CandidateAssertion,
        corpus_hashes: List[str],
    ) -> float:
        """Novelty relative to the set of already-seen canonical hashes."""
        if candidate.canonical_hash and candidate.canonical_hash in corpus_hashes:
            return 0.0
        return 1.0
