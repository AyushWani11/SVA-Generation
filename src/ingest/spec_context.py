"""
VERIFY V2 — Spec Context Builder
==================================
Loads the design_specs.json and decomposes it into typed SpecClauses.
Optionally uses the LLM for SANGAM signal mapping and ChIRAAG breakdown.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import (
    IntentType, RTLContext, SpecClause, SpecContext,
)


class SpecContextBuilder:
    """Build a SpecContext from a JSON spec file."""

    # keyword → IntentType mapping for automatic clause classification
    _INTENT_KEYWORDS = {
        IntentType.RESET: ["reset", "initialization", "initial", "power-on", "rst"],
        IntentType.SAFETY: ["prevent", "never", "overflow", "underflow", "mutual exclusion",
                            "must not", "shall not", "forbidden", "exclusive"],
        IntentType.LIVENESS: ["eventually", "must happen", "shall be granted",
                              "guaranteed", "response"],
        IntentType.TIMING: ["cycle", "latency", "clock", "delay", "within"],
    }

    def __init__(self, llm=None):
        """
        Args:
            llm: Optional LLMInterface for SANGAM / ChIRAAG enrichment.
        """
        self._llm = llm

    # ── public API ────────────────────────────────────────────────────

    def build(
        self,
        spec_path: str,
        design_key: str,
        rtl_ctx: RTLContext,
    ) -> SpecContext:
        """Load spec JSON, decompose into clauses, and optionally map signals."""
        raw_spec = self._load_spec(spec_path, design_key, rtl_ctx.module_name)

        if not raw_spec:
            return SpecContext(
                design_key=design_key,
                design_name=rtl_ctx.module_name,
                description="",
            )

        design_name = raw_spec.get("name", design_key)
        description = raw_spec.get("description", design_name)

        clauses = self.decompose_clauses(raw_spec, design_key)
        clauses = self.map_terms_to_signals(clauses, rtl_ctx)

        signal_descs: Dict[str, str] = raw_spec.get("signals", {})

        return SpecContext(
            design_key=design_key,
            design_name=design_name,
            description=description,
            clauses=clauses,
            signal_descriptions=signal_descs,
        )

    # ── spec loading ──────────────────────────────────────────────────

    def _load_spec(
        self, spec_path: str, design_key: str, module_name: str
    ) -> Dict[str, Any]:
        """Load the spec JSON and resolve the correct design entry."""
        p = Path(spec_path)
        if not p.exists():
            return {}
        with open(p, "r", encoding="utf-8") as f:
            all_specs = json.load(f)

        if design_key and design_key in all_specs:
            return all_specs[design_key]

        # Fallback: match by module name
        for key, spec in all_specs.items():
            if key.lower() in module_name.lower():
                return spec
        return {}

    # ── clause decomposition ──────────────────────────────────────────

    def decompose_clauses(
        self, raw_spec: Dict[str, Any], design_key: str
    ) -> List[SpecClause]:
        """Split the raw spec dict into a list of typed SpecClause objects."""
        clauses: List[SpecClause] = []
        clause_idx = 0

        section_intent_map = {
            "reset_behavior": IntentType.RESET,
            "safety_properties": IntentType.SAFETY,
            "timing_constraints": IntentType.TIMING,
            "functionality": IntentType.INVARIANT,
        }

        for section_key, default_intent in section_intent_map.items():
            items = raw_spec.get(section_key, [])
            if isinstance(items, str):
                items = [items]
            for item in items:
                intent = self._classify_clause(item, default_intent)
                clause_idx += 1
                clauses.append(SpecClause(
                    clause_id=f"{design_key}.{intent.value.lower()}.{clause_idx}",
                    intent=intent,
                    text=item,
                ))

        return clauses

    def _classify_clause(self, text: str, default: IntentType) -> IntentType:
        """Heuristic: override the default intent if strong keywords are found."""
        lower = text.lower()
        for intent, keywords in self._INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw in lower:
                    return intent
        return default

    # ── signal mapping ────────────────────────────────────────────────

    def map_terms_to_signals(
        self, clauses: List[SpecClause], rtl_ctx: RTLContext
    ) -> List[SpecClause]:
        """Map each clause's text to the RTL signals it references."""
        sig_names = set(rtl_ctx.signals.keys())
        for clause in clauses:
            # Simple substring match of signal names in clause text
            found = [s for s in sig_names if re.search(rf"\b{re.escape(s)}\b", clause.text, re.IGNORECASE)]
            clause.mapped_signals = sorted(set(clause.mapped_signals + found))
        return clauses
