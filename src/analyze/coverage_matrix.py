"""
VERIFY V2 — Coverage Matrix
==============================
Maps accepted assertions to the specification clauses they cover.
"""

import re
from typing import Dict, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import CandidateAssertion, SpecClause


class CoverageMatrix:
    """Map assertions to spec clauses by signal overlap and keyword matching."""

    def map_assertions_to_spec(
        self,
        assertions: List[CandidateAssertion],
        clauses: List[SpecClause],
    ) -> Dict[str, List[str]]:
        """
        Returns {candidate_id: [clause_id, ...]} for every assertion
        that covers at least one spec clause.
        """
        coverage: Dict[str, List[str]] = {}

        for cand in assertions:
            matched_clauses: List[str] = []

            # Check explicit refs first
            if cand.spec_clause_refs:
                matched_clauses.extend(cand.spec_clause_refs)

            # Heuristic: signal overlap
            cand_sigs = set(cand.used_signals)
            for clause in clauses:
                clause_sigs = set(clause.mapped_signals)
                if cand_sigs & clause_sigs:
                    if clause.clause_id not in matched_clauses:
                        matched_clauses.append(clause.clause_id)

            # Heuristic: keyword overlap between clause text and assertion
            for clause in clauses:
                words = set(re.findall(r"\b\w{4,}\b", clause.text.lower()))
                assertion_words = set(re.findall(r"\b\w{4,}\b", cand.assertion_text.lower()))
                overlap = words & assertion_words
                if len(overlap) >= 2 and clause.clause_id not in matched_clauses:
                    matched_clauses.append(clause.clause_id)

            if matched_clauses:
                coverage[cand.candidate_id] = matched_clauses

        return coverage
