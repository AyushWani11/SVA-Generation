"""
VERIFY V2 — Metrics Computation
==================================
Utility to derive PipelineMetrics from pipeline data.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import (
    AssertionStatus, PipelineMetrics,
    CandidateAssertion, GateResult, ValidationResult, RefinementAction,
)
from typing import List


def compute_metrics(
    candidates: List[CandidateAssertion],
    gate_results: List[GateResult],
    validation_results: List[ValidationResult],
    refinement_actions: List[RefinementAction],
    final_kept: int,
    llm_calls: int,
    total_runtime_sec: float,
) -> PipelineMetrics:
    """Derive a PipelineMetrics object from raw pipeline data."""
    gated_in = sum(1 for g in gate_results if g.accepted)
    syntax_ok = sum(
        1 for v in validation_results
        if v.status in (AssertionStatus.SYNTAX_OK_ONLY,
                        AssertionStatus.PROVEN_FORMAL,
                        AssertionStatus.DISPROVEN_CEX)
    )
    proven = sum(1 for v in validation_results if v.status == AssertionStatus.PROVEN_FORMAL)
    disproven = sum(1 for v in validation_results if v.status == AssertionStatus.DISPROVEN_CEX)
    refined = sum(1 for r in refinement_actions if r.revised_assertion_text is not None)

    return PipelineMetrics(
        total_candidates=len(candidates),
        gated_in=gated_in,
        syntax_ok=syntax_ok,
        proven_formal=proven,
        disproven=disproven,
        refined=refined,
        final_kept=final_kept,
        llm_calls=llm_calls,
        total_runtime_sec=round(total_runtime_sec, 2),
    )
