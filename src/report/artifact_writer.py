"""
VERIFY V2 — Artifact Writer
==============================
Writes final assertion files, JSON reports, and pipeline logs.
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import (
    CandidateAssertion, PipelineArtifact, AssertionAnalysis,
)


class ArtifactWriter:
    """Persist pipeline outputs to disk."""

    # ── public API ────────────────────────────────────────────────────

    def write_assertions(
        self, path: str, final_assertions: List[CandidateAssertion],
        analyses: List[AssertionAnalysis] = None,
    ) -> None:
        """Write the final .sv assertion file."""
        analyses = analyses or []
        analysis_map = {a.candidate_id: a for a in analyses}

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        with open(p, "w", encoding="utf-8") as f:
            f.write(f"// VERIFY V2 Framework — Generated Assertions\n")
            f.write(f"// Generated: {datetime.now().isoformat()}\n")
            f.write(f"// Total Assertions: {len(final_assertions)}\n\n")

            for i, cand in enumerate(final_assertions):
                a = analysis_map.get(cand.candidate_id)
                intent = a.final_intent.value if a else (cand.intent_hint.value if cand.intent_hint else "?")
                score = a.usefulness_score if a else 0
                f.write(f"\n// === Assertion {i+1} [{intent}] (usefulness: {score:.2f}) ===\n")
                f.write(cand.assertion_text + "\n")

    def write_report(self, path: str, artifact: PipelineArtifact) -> None:
        """Write the full JSON report matching the V2 schema."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        report = self._artifact_to_dict(artifact)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

    def write_logs(self, dir_path: str, artifact: PipelineArtifact) -> None:
        """Write a human-readable pipeline log."""
        d = Path(dir_path)
        d.mkdir(parents=True, exist_ok=True)

        log_path = d / f"{artifact.rtl_context.module_name}_pipeline_v2.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"VERIFY V2 Pipeline Log\n")
            f.write(f"Run ID: {artifact.run_id}\n")
            f.write(f"Design: {artifact.rtl_context.module_name}\n")
            f.write(f"RTL:    {artifact.rtl_context.rtl_path}\n\n")

            m = artifact.metrics
            f.write(f"--- Metrics ---\n")
            f.write(f"Candidates generated: {m.total_candidates}\n")
            f.write(f"Passed pre-formal gate: {m.gated_in}\n")
            f.write(f"Syntax OK: {m.syntax_ok}\n")
            f.write(f"Proven (formal): {m.proven_formal}\n")
            f.write(f"Disproven (CEX): {m.disproven}\n")
            f.write(f"Refined: {m.refined}\n")
            f.write(f"Final kept: {m.final_kept}\n")
            f.write(f"LLM calls: {m.llm_calls}\n")
            f.write(f"Total runtime: {m.total_runtime_sec:.1f}s\n")

    # ── serialization ─────────────────────────────────────────────────

    def _artifact_to_dict(self, artifact: PipelineArtifact) -> dict:
        """Convert PipelineArtifact to the V2 JSON schema."""
        return {
            "run_id": artifact.run_id,
            "metadata": {
                "rtl_path": artifact.rtl_context.rtl_path,
                "design": artifact.rtl_context.module_name,
            },
            "contexts": {
                "rtl": {
                    "module_name": artifact.rtl_context.module_name,
                    "signals_count": len(artifact.rtl_context.signals),
                    "parameters": artifact.rtl_context.parameters,
                    "fsm_states": artifact.rtl_context.fsm_states,
                    "clock_candidates": artifact.rtl_context.clock_candidates,
                    "reset_candidates": artifact.rtl_context.reset_candidates,
                },
                "spec": {
                    "design_key": artifact.spec_context.design_key,
                    "design_name": artifact.spec_context.design_name,
                    "clauses_count": len(artifact.spec_context.clauses),
                },
                "trace": {
                    "source": artifact.trace_context.source,
                    "cycles": artifact.trace_context.cycles,
                    "invariants_count": len(artifact.trace_context.mined_invariants),
                },
            },
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "assertion_text": c.assertion_text,
                    "source_strategy": c.source_strategy,
                    "source_prompt_id": c.source_prompt_id,
                    "used_signals": c.used_signals,
                    "spec_clause_refs": c.spec_clause_refs,
                }
                for c in artifact.candidates
            ],
            "gate_results": [
                {
                    "candidate_id": g.candidate_id,
                    "accepted": g.accepted,
                    "reject_reason": g.reject_reason,
                    "canonical_hash": g.canonical_hash,
                    "diagnostics": g.diagnostics,
                }
                for g in artifact.gate_results
            ],
            "validation_results": [
                {
                    "candidate_id": v.candidate_id,
                    "status": v.status.value if hasattr(v.status, 'value') else v.status,
                    "tool": v.tool,
                    "message": v.message,
                    "proof_depth": v.proof_depth,
                    "runtime_sec": v.runtime_sec,
                }
                for v in artifact.validation_results
            ],
            "refinement_actions": [
                {
                    "candidate_id": r.candidate_id,
                    "iteration": r.iteration,
                    "verdict": r.verdict,
                    "consumed_cex": r.consumed_cex,
                }
                for r in artifact.refinement_actions
            ],
            "analysis": {
                "classification": {a.candidate_id: a.final_intent.value for a in artifact.analyses},
                "redundancy_edges": [],  # populated by orchestrator
                "scores": {
                    a.candidate_id: {
                        "usefulness": round(a.usefulness_score, 3),
                        "novelty": round(a.novelty_score, 3),
                    }
                    for a in artifact.analyses
                },
                "coverage": {
                    a.candidate_id: a.coverage_clauses
                    for a in artifact.analyses
                    if a.coverage_clauses
                },
            },
            "metrics": asdict(artifact.metrics),
        }
