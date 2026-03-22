"""
VERIFY V2 — Prompt Engine
===========================
Thin wrapper over the existing templates.py that adds provenance tracking.
"""

import hashlib
from typing import Any, Dict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "prompts"))

from templates import (
    SPEC_DRIVEN_GENERATION,
    RTL_DRIVEN_GENERATION,
    INVARIANT_SEEDED_GENERATION,
    COUNTEREXAMPLE_ANALYSIS,
    SYNTAX_CORRECTION,
    ASSERTION_CLASSIFICATION,
    REDUNDANCY_ANALYSIS,
    HOLISTIC_GENERATION,
    SANGAM_MAPPING,
    CHIRAAG_SEMANTIC_BREAKDOWN,
    CHIRAAG_CONTEXT_GENERATION,
)

# Template registry mapping strategy names to template strings
_TEMPLATE_REGISTRY: Dict[str, str] = {
    "spec_driven": SPEC_DRIVEN_GENERATION,
    "rtl_driven": RTL_DRIVEN_GENERATION,
    "invariant_seeded": INVARIANT_SEEDED_GENERATION,
    "holistic": HOLISTIC_GENERATION,
    "chiraag_generation": CHIRAAG_CONTEXT_GENERATION,
    "sangam_mapping": SANGAM_MAPPING,
    "chiraag_breakdown": CHIRAAG_SEMANTIC_BREAKDOWN,
    "counterexample_analysis": COUNTEREXAMPLE_ANALYSIS,
    "syntax_correction": SYNTAX_CORRECTION,
    "assertion_classification": ASSERTION_CLASSIFICATION,
    "redundancy_analysis": REDUNDANCY_ANALYSIS,
}


class PromptEngine:
    """Render prompt templates with provenance tracking."""

    def render(self, template_name: str, payload: Dict[str, Any]) -> str:
        """Render a named template with the given payload dict."""
        template = _TEMPLATE_REGISTRY.get(template_name)
        if template is None:
            raise KeyError(f"Unknown template: {template_name}")
        return template.format(**payload)

    def prompt_id(self, template_name: str, payload: Dict[str, Any]) -> str:
        """Return a deterministic hash identifying this (template, payload) pair."""
        rendered = self.render(template_name, payload)
        digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:12]
        return f"{template_name}:{digest}"
