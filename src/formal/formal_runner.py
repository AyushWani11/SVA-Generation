"""
VERIFY V2 — Formal Runner
============================
Native SymbiYosys (sby) execution wrapper for V2.
Bypasses the V1 verifier entirely to provide deterministic mathematical proofs.
"""

import time
import subprocess
from pathlib import Path
from typing import List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import (
    AssertionStatus, CandidateAssertion, RTLContext, ValidationResult,
)
from formal.wrapper_builder import WrapperBuilder
from formal.cex_parser import CexParser


class FormalRunner:
    """Formal validation of gated candidates via native SymbiYosys."""

    def __init__(self, work_dir: str = "output/formal"):
        self.work_dir = Path(work_dir).resolve()
        self._wrapper = WrapperBuilder()
        self._cex = CexParser()

    def get_tool_status(self) -> str:
        """Check if SymbiYosys is installed and available in the system PATH."""
        try:
            subprocess.run(["sby", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return "Formal Toolchain: ✓ SymbiYosys (sby) Available"
        except FileNotFoundError:
            return "Formal Toolchain: ✗ SymbiYosys NOT FOUND in PATH"

    def _run_symbiyosys_native(
        self, 
        rtl_ctx: RTLContext, 
        candidate: CandidateAssertion, 
        depth: int
    ) -> ValidationResult:
        """Natively execute SymbiYosys for a single assertion."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Build and write the SV Wrapper
        wrapper_sv = self._wrapper.build_bound_wrapper(rtl_ctx, candidate.assertion_text)
        wrapper_path = self.work_dir / f"wrapper_{candidate.candidate_id}.sv"
        wrapper_path.write_text(wrapper_sv)

        # 2. Build the SymbiYosys (.sby) configuration script
        sby_path = self.work_dir / f"run_{candidate.candidate_id}.sby"
        rtl_full_path = Path(rtl_ctx.rtl_path).resolve()
        
        # FIX: Use quoted absolute paths directly in the script. 
        # This prevents SBY from crashing on directories with spaces.
        sby_content = f"""[options]
mode bmc
depth {depth}

[engines]
smtbmc boolector

[script]
read -formal -sv "{rtl_full_path}"
read -formal -sv "{wrapper_path}"
prep -top {rtl_ctx.module_name}
"""
        sby_path.write_text(sby_content)

        # 3. Execute the Subprocess
        t0 = time.time()
        try:
            result = subprocess.run(
                ["sby", "-f", sby_path.name],
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                timeout=60 # 60-second timeout per assertion
            )
            output = result.stdout + result.stderr
            
        except subprocess.TimeoutExpired:
            return ValidationResult(
                candidate_id=candidate.candidate_id,
                status=AssertionStatus.TIMEOUT,
                tool="symbiyosys",
                message="Formal proof timed out.",
                runtime_sec=time.time() - t0
            )
        except Exception as e:
            return ValidationResult(
                candidate_id=candidate.candidate_id,
                status=AssertionStatus.TOOL_ERROR,
                tool="symbiyosys",
                message=f"Tool execution failed: {str(e)}",
                runtime_sec=time.time() - t0
            )

        runtime = round(time.time() - t0, 3)

        # 4. Parse the Verdict from Terminal Output
        status = AssertionStatus.UNKNOWN
        cex_text = None
        message = "Unknown verdict."

        if "DONE (PASS)" in output:
            status = AssertionStatus.PROVEN_FORMAL
            message = f"Proven up to depth {depth}."
        elif "DONE (FAIL)" in output:
            status = AssertionStatus.DISPROVEN_CEX
            message = "Counterexample found."
            raw_cex = self._cex.parse(output, candidate.property_name)
            if raw_cex:
                cex_text = self._cex.minimise(raw_cex)
        elif "ERROR" in output or "Syntax error" in output:
            status = AssertionStatus.SYNTAX_ERROR
            message = "Syntax or structural error detected by Yosys."

        return ValidationResult(
            candidate_id=candidate.candidate_id,
            status=status,
            tool="symbiyosys",
            message=message,
            proof_depth=depth if status == AssertionStatus.PROVEN_FORMAL else None,
            counterexample=cex_text,
            error_log=output if status != AssertionStatus.PROVEN_FORMAL else "",
            runtime_sec=runtime
        )

    def validate(
        self,
        rtl_ctx: RTLContext,
        gated_candidates: List[CandidateAssertion],
        depth: int = 20,
    ) -> List[ValidationResult]:
        """
        Validate a list of gated candidates using native V2 SymbiYosys integration.
        """
        results: List[ValidationResult] = []

        for cand in gated_candidates:
            result = self._run_symbiyosys_native(rtl_ctx, cand, depth)
            results.append(result)

        return results