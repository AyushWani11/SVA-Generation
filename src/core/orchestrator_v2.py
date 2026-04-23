"""
VERIFY V2 — Orchestrator
===========================
Dependency-injected orchestrator that runs the full 8-step V2 pipeline.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import (
    AssertionStatus, AssertionAnalysis, CandidateAssertion,
    GateResult, PipelineArtifact, PipelineMetrics,
    RTLContext, SpecContext, TraceContext, ValidationResult,
)
from ingest.rtl_context import RTLContextBuilder
from ingest.spec_context import SpecContextBuilder
from ingest.trace_context import TraceContextBuilder
from generate.candidate_generator import CandidateGenerator
from generate.prompt_engine import PromptEngine
from gate.pre_formal_gate import PreFormalGate
from formal.formal_runner import FormalRunner
from refine.refinement_loop import RefinementLoop
from analyze.classifier import AssertionClassifier
from analyze.redundancy_graph import RedundancyGraph
from analyze.scoring import ScoringEngine
from analyze.coverage_matrix import CoverageMatrix
from report.artifact_writer import ArtifactWriter
from report.metrics import compute_metrics
from report.critical_analyzer import CriticalAnalyzer

class VerifyOrchestratorV2:
    """
    Main V2 pipeline orchestrator.

    Execution order inside run():
      1. Build contexts (RTL, Spec, Trace)
      2. Generate candidates
      3. Apply pre-formal gate
      4. Validate formally
      5. Refine failed candidates
      6. Re-validate refined assertions
      7. Analyze accepted set
      8. Write artifacts + metrics
    """

    def __init__(
        self,
        llm,
        rtl_builder: Optional[RTLContextBuilder] = None,
        spec_builder: Optional[SpecContextBuilder] = None,
        trace_builder: Optional[TraceContextBuilder] = None,
        generator: Optional[CandidateGenerator] = None,
        gate: Optional[PreFormalGate] = None,
        formal: Optional[FormalRunner] = None,
        refiner: Optional[RefinementLoop] = None,
        classifier: Optional[AssertionClassifier] = None,
        redundancy: Optional[RedundancyGraph] = None,
        scoring: Optional[ScoringEngine] = None,
        coverage: Optional[CoverageMatrix] = None,
        writer: Optional[ArtifactWriter] = None,
        output_dir: str = "output_v2",
    ):
        self._llm = llm
        self._rtl_builder = rtl_builder or RTLContextBuilder()
        self._spec_builder = spec_builder or SpecContextBuilder(llm=llm)
        self._trace_builder = trace_builder or TraceContextBuilder()
        self._pe = PromptEngine()
        self._generator = generator or CandidateGenerator(llm, self._pe)
        self._gate = gate or PreFormalGate()
        self._formal = formal or FormalRunner(work_dir=str(Path(output_dir) / "formal"))
        self._refiner = refiner or RefinementLoop(llm, self._pe)
        self._classifier = classifier or AssertionClassifier()
        self._redundancy = redundancy or RedundancyGraph()
        self._scoring = scoring or ScoringEngine()
        self._coverage = coverage or CoverageMatrix()
        self._writer = writer or ArtifactWriter()
        self._output_dir = Path(output_dir)

    # ── main entry point ──────────────────────────────────────────────

    def run(
        self,
        rtl_path: str,
        spec_path: str,
        design_key: str,
        vcd_path: Optional[str] = None,
        max_refine_iter: int = 3,
        max_refine_budget: int = 10,
    ) -> PipelineArtifact:
        """Execute the full V2 pipeline and return a PipelineArtifact."""
        run_id = f"{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}_{design_key}"
        t0 = time.time()
        self._log("=" * 60)
        self._log("VERIFY V2 Framework — Starting Pipeline")
        self._log(f"Run ID : {run_id}")
        self._log(f"Design : {design_key}")
        self._log("=" * 60)

        # ── Step 1: Build contexts ────────────────────────────────────
        self._log("\n[A] Building contexts …")
        rtl_ctx = self._rtl_builder.build(rtl_path)
        self._log(f"  RTL: {rtl_ctx.module_name}  signals={len(rtl_ctx.signals)}  "
                  f"FSM states={len(rtl_ctx.fsm_states)}")

        spec_ctx = self._spec_builder.build(spec_path, design_key, rtl_ctx)
        self._log(f"  Spec: {len(spec_ctx.clauses)} clauses")

        trace_ctx = self._trace_builder.build(rtl_ctx, vcd_path)
        self._log(f"  Trace: {trace_ctx.source}  {trace_ctx.cycles} cycles  "
                  f"{len(trace_ctx.mined_invariants)} invariants")

        # ── Step 2: Generate candidates ───────────────────────────────
        self._log("\n[B] Generating candidate assertions …")
        candidates = self._generator.generate(rtl_ctx, spec_ctx, trace_ctx)
        self._log(f"  Generated {len(candidates)} raw candidates")

        # ── Step 3: Pre-formal gate ───────────────────────────────────
        self._log("\n[C] Applying pre-formal quality gate …")
        gate_results: List[GateResult] = []
        gated_candidates: List[CandidateAssertion] = []
        for cand in candidates:
            gr = self._gate.evaluate(cand, rtl_ctx)
            gate_results.append(gr)
            if gr.accepted:
                cand.canonical_hash = gr.canonical_hash
                if gr.fuzzy_corrections:
                    self._log(
                        f"  [FUZZY] {cand.candidate_id}: "
                        + ", ".join(
                            f"{orig} → {fixed}"
                            for orig, fixed in gr.fuzzy_corrections.items()
                        )
                    )
                gated_candidates.append(cand)

        rejected = len(candidates) - len(gated_candidates)
        self._log(f"  Accepted: {len(gated_candidates)}  Rejected: {rejected}")

        # ── Step 4: Formal validation ─────────────────────────────────
        self._log("\n[D] Formal validation …")
        self._log(f"  {self._formal.get_tool_status()}")
        validation_results: List[ValidationResult] = []
        if gated_candidates:
            validation_results = self._formal.validate(rtl_ctx, gated_candidates)
            for vr in validation_results:
                self._log(f"  {vr.status.value:18s}  {vr.candidate_id}")
                
                # --- NEW DEBUG PRINT ---
                if vr.status == AssertionStatus.SYNTAX_ERROR:
                    # Extract just the lines from Yosys containing the error
                    for line in vr.error_log.split('\n'):
                        if "ERROR:" in line or "syntax error" in line.lower():
                            self._log(f"      [Yosys] {line.strip()}")

        # ── Step 5: Refine failed candidates ──────────────────────────
        self._log("\n[E] Refinement loop …")
        failed = [v for v in validation_results
                  if v.status in (AssertionStatus.SYNTAX_ERROR, AssertionStatus.DISPROVEN_CEX)]
        cand_map = {c.candidate_id: c for c in gated_candidates}
        revised, refinement_actions = self._refiner.run(
            rtl_ctx, spec_ctx, failed, cand_map,
            max_iter=max_refine_iter,
            max_total_api_calls=max_refine_budget,
        )
        self._log(f"  Refined {len(revised)} candidates from {len(failed)} failures")

        # ── Step 6: Re-validate refined ───────────────────────────────
        self._log("\n[D'] Re-validating refined assertions …")
        re_validation: List[ValidationResult] = []
        if revised:
            re_validation = self._formal.validate(rtl_ctx, revised)
            validation_results.extend(re_validation)
            for vr in re_validation:
                self._log(f"  {vr.status.value:18s}  {vr.candidate_id}")

        # ── Step 7: Analyze accepted set ──────────────────────────────
        self._log("\n[F] Analyzing accepted assertions …")
        accepted_statuses = {AssertionStatus.PROVEN_FORMAL, AssertionStatus.SYNTAX_OK_ONLY}
        accepted_ids = {v.candidate_id for v in validation_results if v.status in accepted_statuses}
        all_cands = gated_candidates + revised
        accepted_cands = [c for c in all_cands if c.candidate_id in accepted_ids]

        # Build validation-result map for scoring
        vr_map: Dict[str, ValidationResult] = {v.candidate_id: v for v in validation_results}

        analyses: List[AssertionAnalysis] = []
        corpus_hashes: List[str] = [c.canonical_hash for c in accepted_cands if c.canonical_hash]
        coverage_map = self._coverage.map_assertions_to_spec(accepted_cands, spec_ctx.clauses)

        for cand in accepted_cands:
            intent = self._classifier.classify(cand.assertion_text)
            vr = vr_map.get(cand.candidate_id)
            status = vr.status if vr else AssertionStatus.UNKNOWN
            u_score = self._scoring.usefulness(cand.assertion_text, intent, status)
            n_score = self._scoring.novelty(cand, corpus_hashes)

            analyses.append(AssertionAnalysis(
                candidate_id=cand.candidate_id,
                final_intent=intent,
                usefulness_score=u_score,
                novelty_score=n_score,
                coverage_clauses=coverage_map.get(cand.candidate_id, []),
            ))

        # Redundancy
        redun_adj = self._redundancy.build(accepted_cands)
        for a in analyses:
            a.redundant_with = redun_adj.get(a.candidate_id, [])

        self._log(f"  Accepted assertions: {len(accepted_cands)}")
        if analyses:
            avg_u = sum(a.usefulness_score for a in analyses) / len(analyses)
            self._log(f"  Mean usefulness: {avg_u:.2f}")

        # ── Step 8: Write artifacts + metrics ─────────────────────────
        self._log("\n[G] Writing artifacts …")
        elapsed = time.time() - t0
        llm_calls = self._llm.call_count if hasattr(self._llm, "call_count") else 0

        metrics = compute_metrics(
            candidates, gate_results, validation_results,
            refinement_actions, len(accepted_cands), llm_calls, elapsed,
        )

        artifact = PipelineArtifact(
            run_id=run_id,
            rtl_context=rtl_ctx,
            spec_context=spec_ctx,
            trace_context=trace_ctx,
            candidates=candidates,
            gate_results=gate_results,
            validation_results=validation_results,
            refinement_actions=refinement_actions,
            analyses=analyses,
            metrics=metrics,
        )

        # Generate Critical Analysis Markdown Report
        print(f"[{run_id}] Generating Critical Analysis...")
        critical_analyzer = CriticalAnalyzer()
        markdown_report = critical_analyzer.generate_report(artifact)
        
        report_path = Path(self._output_dir) / "reports" / f"{rtl_ctx.module_name}_critical_analysis.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(markdown_report)
        print(f"[{run_id}]  Report written to {report_path}")


        # Ensure output dirs exist
        (self._output_dir / "assertions").mkdir(parents=True, exist_ok=True)
        (self._output_dir / "reports").mkdir(parents=True, exist_ok=True)
        (self._output_dir / "logs").mkdir(parents=True, exist_ok=True)

        self._writer.write_assertions(
            str(self._output_dir / "assertions" / f"{rtl_ctx.module_name}_assertions.sv"),
            accepted_cands, analyses,
        )
        self._writer.write_report(
            str(self._output_dir / "reports" / f"{rtl_ctx.module_name}_report.json"),
            artifact,
        )
        self._writer.write_logs(str(self._output_dir / "logs"), artifact)

        self._log(f"\nPipeline completed in {elapsed:.1f}s")
        self._log(f"Results saved to: {self._output_dir}")

        return artifact

    # ── logging ───────────────────────────────────────────────────────

    @staticmethod
    def _log(msg: str):
        print(msg)
