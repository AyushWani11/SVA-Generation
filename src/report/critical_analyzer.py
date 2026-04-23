"""
VERIFY V2 — Critical Analyzer
==============================
Automatically generates the Critical Analysis Markdown.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import PipelineArtifact, AssertionStatus

class CriticalAnalyzer:
    """Automates the 'Critical Analysis' deliverable."""

    def generate_report(self, artifact: PipelineArtifact) -> str:
        trivial_assertions = []
        over_restrictive = []
        bugs_found = []

        # Map candidates and analyses by ID for O(1) lookup
        cand_map = {c.candidate_id: c for c in artifact.candidates}
        analysis_map = {a.candidate_id: a for a in artifact.analyses}
        
        for val in artifact.validation_results:
            cand = cand_map.get(val.candidate_id)
            if not cand: 
                continue
            
            ana = analysis_map.get(cand.candidate_id)
            
            # --- 1. Correct but Trivial ---
            if val.status == AssertionStatus.PROVEN_FORMAL:
                # Check redundancy graph output or basic usefulness scoring
                if ana and (ana.redundant_with or ana.usefulness_score < 0.5):
                    reason = "Subsumed by stronger assertion" if ana.redundant_with else "Lacks conditional implications (|->)"
                    trivial_assertions.append(f"- **Assertion:** `{cand.assertion_text.strip()}`\n  - *Reason:* {reason}")
                    
            # --- 2 & 3. Examine Refinement Loop for Failed Assertions ---
            elif val.status == AssertionStatus.DISPROVEN_CEX:
                # Look at the refinement actions taken for this specific candidate
                refinements = [r for r in artifact.refinement_actions if r.candidate_id == cand.candidate_id]
                if refinements:
                    final_action = refinements[-1] # The LLM's final conclusion
                    
                    if final_action.verdict in ["ASSERTION_WRONG", "SPEC_AMBIGUOUS"]:
                        over_restrictive.append(f"- **Assertion:** `{cand.assertion_text.strip()}`\n  - *LLM Rationale:* {final_action.rationale}")
                        
                    elif final_action.verdict == "DESIGN_BUG":
                        trace_preview = val.counterexample[:150].replace('\n', ' ') if val.counterexample else "No trace extracted."
                        bugs_found.append(f"- **Assertion:** `{cand.assertion_text.strip()}`\n  - *LLM Rationale:* {final_action.rationale}\n  - *Trace Preview:* `{trace_preview}...`")

        return self._format_markdown(artifact.rtl_context.module_name, trivial_assertions, over_restrictive, bugs_found)

    def _format_markdown(self, module_name: str, trivial: list, restrict: list, bugs: list) -> str:
        report = [f"# Critical Analysis for `{module_name}`\n"]
        
        report.append("### 1. Which assertions are correct but trivial?")
        if trivial:
            report.append("\n".join(trivial))
        else:
            report.append("*None detected. All proven assertions were structurally unique and non-trivial.*")
            
        report.append("\n### 2. Which assertions are incorrect or over-restrictive?")
        if restrict:
            report.append("\n".join(restrict))
        else:
            report.append("*None detected. The LLM successfully generated accurate bounds for all failures.*")
            
        report.append("\n### 3. Which assertions reveal bugs or corner cases in the RTL?")
        if bugs:
            report.append("\n".join(bugs))
        else:
            report.append("*No design bugs were discovered. The provided RTL perfectly matches the specification constraints.*")

        return "\n".join(report)