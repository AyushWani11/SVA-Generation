"""
VERIFY V2 — Refinement Loop
==============================
Configurable CEX-driven assertion repair with iteration budget.
Removes V1's single-iteration clamp.
"""

import uuid
import re
from typing import List, Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import (
    CandidateAssertion, RTLContext, SpecContext,
    ValidationResult, RefinementAction, AssertionStatus, IntentType,
)
from generate.prompt_engine import PromptEngine


class RefinementLoop:
    """Iteratively refine failed assertions using LLM + CEX feedback."""

    def __init__(self, llm, prompt_engine: Optional[PromptEngine] = None):
        self._llm = llm
        self._pe = prompt_engine or PromptEngine()

    # ── public API ────────────────────────────────────────────────────

    def run(
        self,
        rtl_ctx: RTLContext,
        spec_ctx: SpecContext,
        failed_results: List[ValidationResult],
        candidates_map: dict,  # candidate_id → CandidateAssertion
        max_iter: int = 3,
        max_total_api_calls: int = 10,
    ) -> Tuple[List[CandidateAssertion], List[RefinementAction]]:
        """
        Attempt to repair each failed candidate up to *max_iter* times.

        Hard limits:
          • max_iter            — per-candidate maximum iterations.
          • max_total_api_calls — global session budget; when exhausted the
                                   remaining candidates are logged as
                                   BUDGET_EXHAUSTED without further LLM calls.

        Returns:
            revised_candidates — new CandidateAssertions (one per successful repair)
            actions            — full log of every refinement attempt
        """
        revised: List[CandidateAssertion] = []
        actions: List[RefinementAction] = []
        improvements = 0
        api_calls_used = 0          # global counter across all candidates

        for result in failed_results:
            cand = candidates_map.get(result.candidate_id)
            if cand is None:
                continue

            # ── Global budget guard ──────────────────────────────────────
            if api_calls_used >= max_total_api_calls:
                actions.append(RefinementAction(
                    candidate_id=cand.candidate_id,
                    iteration=0,
                    verdict="BUDGET_EXHAUSTED",
                    rationale=(
                        f"Global API budget of {max_total_api_calls} calls reached; "
                        "skipping further refinement."
                    ),
                ))
                continue

            last_text: Optional[str] = None  # for convergence detection

            for iteration in range(1, max_iter + 1):
                if self.should_stop(iteration, improvements, max_iter):
                    break

                action = self.propose_fix(result, rtl_ctx, spec_ctx, cand, iteration)
                actions.append(action)
                api_calls_used += 1

                # ── UNFIXABLE early break ──────────────────────────────
                if action.verdict == "UNFIXABLE":
                    break

                # ── Convergence guard ─────────────────────────────────────
                new_text = action.revised_assertion_text
                if new_text and new_text == last_text:
                    # LLM returned identical broken text — no point continuing
                    actions.append(RefinementAction(
                        candidate_id=cand.candidate_id,
                        iteration=iteration,
                        verdict="UNFIXABLE_STALL",
                        rationale="LLM produced the same assertion twice; convergence stall detected.",
                    ))
                    break
                last_text = new_text

                if action.revised_assertion_text:
                    improvements += 1
                    new_cid = f"ref_{uuid.uuid4().hex[:8]}"
                    revised.append(CandidateAssertion(
                        candidate_id=new_cid,
                        assertion_text=action.revised_assertion_text,
                        property_name=self._extract_prop_name(action.revised_assertion_text),
                        intent_hint=cand.intent_hint,
                        source_strategy=f"refine_{cand.source_strategy}",
                        source_prompt_id=cand.source_prompt_id,
                        used_signals=cand.used_signals,
                        spec_clause_refs=cand.spec_clause_refs,
                        metadata={"parent_id": cand.candidate_id, "iteration": iteration},
                    ))
                    break  # move to next failed candidate once we get a fix

                # ── Per-iteration global budget check ─────────────────────
                if api_calls_used >= max_total_api_calls:
                    break

        return revised, actions

    # ── per-candidate repair ──────────────────────────────────────────

    def propose_fix(
        self,
        result: ValidationResult,
        rtl_ctx: RTLContext,
        spec_ctx: SpecContext,
        candidate: CandidateAssertion,
        iteration: int,
    ) -> RefinementAction:
        """Use the LLM to propose a fix for one failed candidate."""
        if result.status == AssertionStatus.SYNTAX_ERROR:
            return self._fix_syntax(result, rtl_ctx, candidate, iteration)
        if result.status == AssertionStatus.DISPROVEN_CEX:
            return self._fix_cex(result, rtl_ctx, spec_ctx, candidate, iteration)
        # Not fixable
        return RefinementAction(
            candidate_id=candidate.candidate_id,
            iteration=iteration,
            verdict="UNFIXABLE",
            rationale=f"Status {result.status.value} is not refinable.",
        )

    def _fix_syntax(
        self, result, rtl_ctx, candidate, iteration,
    ) -> RefinementAction:
        signal_names = ", ".join(sorted(rtl_ctx.signals.keys()))
        prompt = self._pe.render("syntax_correction", dict(
            assertion_code=candidate.assertion_text,
            error_messages=result.error_log,
            signal_names=signal_names,
        ))
        resp = self._llm.call(prompt, tag=f"syntax_fix_{candidate.candidate_id}")
        revised = resp.assertions[0] if resp.assertions else None
        return RefinementAction(
            candidate_id=candidate.candidate_id,
            iteration=iteration,
            verdict="ASSERTION_WRONG" if revised else "UNFIXABLE",
            revised_assertion_text=revised,
            rationale="LLM syntax repair",
            consumed_cex=False,
        )

    def _fix_cex(
        self, result, rtl_ctx, spec_ctx, candidate, iteration,
    ) -> RefinementAction:
        spec_text = "; ".join(c.text for c in spec_ctx.clauses[:5]) if spec_ctx.clauses else ""
        prompt = self._pe.render("counterexample_analysis", dict(
            design_name=rtl_ctx.module_name,
            assertion_code=candidate.assertion_text,
            counterexample_trace=result.counterexample or "No trace available",
            spec_excerpt=spec_text[:500],
            rtl_excerpt=rtl_ctx.raw_code[:500],
        ))
        resp = self._llm.call(prompt, tag=f"cex_fix_{candidate.candidate_id}")

        verdict = "UNFIXABLE"
        revised = None
        if "ASSERTION_WRONG" in resp.raw_text and resp.assertions:
            verdict = "ASSERTION_WRONG"
            revised = resp.assertions[0]
        elif "DESIGN_BUG" in resp.raw_text:
            verdict = "DESIGN_BUG"

        return RefinementAction(
            candidate_id=candidate.candidate_id,
            iteration=iteration,
            verdict=verdict,
            revised_assertion_text=revised,
            rationale=resp.raw_text[:300],
            consumed_cex=True,
        )

    # ── budget control ────────────────────────────────────────────────

    def should_stop(self, iter_idx: int, improvements: int, budget: int) -> bool:
        """Early stop if we've exhausted the budget or no progress."""
        return iter_idx > budget

    @staticmethod
    def _extract_prop_name(text: str) -> str:
        m = re.search(r"property\s+(\w+)", text)
        return m.group(1) if m else "unknown"
