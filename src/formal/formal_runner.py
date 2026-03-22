"""
VERIFY V2 — Formal Runner
============================
Wraps the existing V1 FormalVerifier with V2 status typing.
Separates compile-only (syntax) from prove (formal proof).
"""

import time
from typing import List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import (
    AssertionStatus, CandidateAssertion, RTLContext, ValidationResult,
)
from formal_verifier import FormalVerifier, VerificationResult as V1Result
from formal.wrapper_builder import WrapperBuilder
from formal.cex_parser import CexParser


# V1 → V2 status mapping
_STATUS_MAP = {
    "PROVEN":         AssertionStatus.PROVEN_FORMAL,
    "COUNTEREXAMPLE": AssertionStatus.DISPROVEN_CEX,
    "SYNTAX_ERROR":   AssertionStatus.SYNTAX_ERROR,
    "TIMEOUT":        AssertionStatus.TIMEOUT,
    "UNKNOWN":        AssertionStatus.UNKNOWN,
}


class FormalRunner:
    """Formal validation of gated candidates via the V1 FormalVerifier."""

    def __init__(self, work_dir: str = "output/formal"):
        self._verifier = FormalVerifier(work_dir=work_dir)
        self._wrapper = WrapperBuilder()
        self._cex = CexParser()

    @property
    def tool_available(self):
        return self._verifier.tool_available

    # ── public API ────────────────────────────────────────────────────

    def validate(
        self,
        rtl_ctx: RTLContext,
        gated_candidates: List[CandidateAssertion],
        depth: int = 20,
    ) -> List[ValidationResult]:
        """
        Validate a list of gated candidates.
        Each candidate is individually verified via the tool chain.
        """
        results: List[ValidationResult] = []

        assertion_texts = [c.assertion_text for c in gated_candidates]
        t0 = time.time()

        v1_results: List[V1Result] = self._verifier.verify_assertions(
            rtl_ctx.rtl_path, assertion_texts, rtl_ctx.module_name,
        )

        elapsed = time.time() - t0
        per_assertion = elapsed / max(len(v1_results), 1)

        for v1r, cand in zip(v1_results, gated_candidates):
            status = _STATUS_MAP.get(v1r.status, AssertionStatus.UNKNOWN)

            # Determine which tool was used
            tool = "regex_standalone"
            for name in ("symbiyosys", "yosys", "iverilog"):
                if self._verifier.tool_available.get(name):
                    tool = name
                    break

            cex_text: Optional[str] = None
            if v1r.counterexample:
                cex_text = self._cex.minimise(v1r.counterexample)

            # Distinguish syntax-only pass from formal proof
            if status == AssertionStatus.PROVEN_FORMAL and tool in ("iverilog", "regex_standalone"):
                status = AssertionStatus.SYNTAX_OK_ONLY

            results.append(ValidationResult(
                candidate_id=cand.candidate_id,
                status=status,
                tool=tool,
                message=v1r.message,
                proof_depth=depth if status == AssertionStatus.PROVEN_FORMAL else None,
                counterexample=cex_text,
                error_log=v1r.error_log,
                runtime_sec=round(per_assertion, 3),
            ))

        return results

    # ── convenience ───────────────────────────────────────────────────

    def run_compile_syntax(
        self, rtl_files: List[str], wrapper_file: str
    ) -> ValidationResult:
        """Syntax-only compile using iverilog/yosys (exposed for direct use)."""
        # Delegate to the V1 verifier's syntax paths
        raise NotImplementedError("Use validate() for the standard path.")

    def run_formal_prove(self, sby_file: str) -> ValidationResult:
        """Run a sby proof (exposed for direct use)."""
        raise NotImplementedError("Use validate() for the standard path.")

    def get_tool_status(self) -> str:
        return self._verifier.get_tool_status()
