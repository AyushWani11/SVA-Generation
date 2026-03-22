"""
VERIFY V2 — Redundancy Graph
===============================
Builds a textual implication / subsumption graph between assertions.
"""

import re
from typing import Dict, List, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import CandidateAssertion


class RedundancyGraph:
    """Detect redundant / subsumed assertions via normalized comparison."""

    def build(
        self, assertions: List[CandidateAssertion]
    ) -> Dict[str, List[str]]:
        """
        Return adjacency dict: assertion_id -> list of assertion_ids it is
        redundant with.
        """
        normed = {a.candidate_id: self._normalize(a.assertion_text) for a in assertions}
        adj: Dict[str, List[str]] = {cid: [] for cid in normed}

        ids = list(normed.keys())
        for i, cid_a in enumerate(ids):
            for cid_b in ids[i + 1:]:
                na, nb = normed[cid_a], normed[cid_b]
                if na == nb:
                    adj[cid_a].append(cid_b)
                    adj[cid_b].append(cid_a)
                elif na in nb:
                    adj[cid_a].append(cid_b)
                elif nb in na:
                    adj[cid_b].append(cid_a)

        return adj

    def implied_edges(
        self, assertions: List[CandidateAssertion]
    ) -> List[Tuple[str, str, str]]:
        """Return [(id_a, id_b, relationship), ...] where relationship is
        'identical', 'subsumes', or 'subsumed_by'."""
        normed = {a.candidate_id: self._normalize(a.assertion_text) for a in assertions}
        edges: List[Tuple[str, str, str]] = []
        ids = list(normed.keys())

        for i, cid_a in enumerate(ids):
            for cid_b in ids[i + 1:]:
                na, nb = normed[cid_a], normed[cid_b]
                if na == nb:
                    edges.append((cid_a, cid_b, "identical"))
                elif na in nb:
                    edges.append((cid_b, cid_a, "subsumes"))
                elif nb in na:
                    edges.append((cid_a, cid_b, "subsumes"))
        return edges

    @staticmethod
    def _normalize(text: str) -> str:
        norm = re.sub(r"//[^\n]*", "", text)
        norm = re.sub(r"\s+", " ", norm).strip()
        norm = re.sub(r"property\s+\w+", "property P", norm)
        norm = re.sub(r"assert\s+property\s*\(\s*\w+\s*\)", "assert property (P)", norm)
        return norm
