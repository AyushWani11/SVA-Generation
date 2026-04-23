"""
VERIFY V2 — Formal Runner
============================
Native SymbiYosys (sby) execution wrapper for V2.
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
        try:
            subprocess.run(["sby", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return "Formal Toolchain: ✓ SymbiYosys (sby) Available"
        except FileNotFoundError:
            return "Formal Toolchain: ✗ SymbiYosys NOT FOUND in PATH"

    def _run_symbiyosys_native(
        self, rtl_ctx: RTLContext, candidate: CandidateAssertion, depth: int
    ) -> ValidationResult:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        wrapper_sv = self._wrapper.build_bound_wrapper(rtl_ctx, candidate.assertion_text)
        wrapper_path = self.work_dir / f"wrapper_{candidate.candidate_id}.sv"
        wrapper_path.write_text(wrapper_sv)

        sby_path = self.work_dir / f"run_{candidate.candidate_id}.sby"
        rtl_full_path = Path(rtl_ctx.rtl_path).resolve()
        
        # CRITICAL FIX: Removed 'multiclock on'. Single-clock mode is highly stable.
        sby_content = f"""[options]
mode bmc
depth {depth}

[engines]
smtbmc boolector

[script]
read_verilog -formal -sv "{rtl_full_path}"
read_verilog -formal -sv "{wrapper_path}"
prep -top {rtl_ctx.module_name}
"""
        sby_path.write_text(sby_content)

        t0 = time.time()
        try:
            result = subprocess.run(
                ["sby", "-f", sby_path.name],
                cwd=str(self.work_dir), capture_output=True, text=True, timeout=60
            )
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return ValidationResult(candidate.candidate_id, AssertionStatus.TIMEOUT, "symbiyosys", "Timeout", runtime_sec=time.time() - t0)
        except Exception as e:
            return ValidationResult(candidate.candidate_id, AssertionStatus.TOOL_ERROR, "symbiyosys", str(e), runtime_sec=time.time() - t0)

        runtime = round(time.time() - t0, 3)
        # Parse the Verdict from Terminal Output
        status = AssertionStatus.UNKNOWN
        cex_text = None
        message = "Unknown verdict."

        # More robust success matching
        if any(x in output for x in ["DONE (PASS)", "Status: passed", "Checking properties: 0 errors"]):
            status = AssertionStatus.PROVEN_FORMAL
            message = f"Proven up to depth {depth}."
        elif any(x in output for x in ["DONE (FAIL)", "Status: failed", "Assertion failed"]):
            status = AssertionStatus.DISPROVEN_CEX
            message = "Counterexample found."
            # ... keep the rest of your CEX parsing logic ...
            raw_cex = self._cex.parse(output, candidate.property_name)
            if raw_cex:
                cex_text = self._cex.minimise(raw_cex)
        elif "ERROR" in output or "Syntax error" in output:
            status = AssertionStatus.SYNTAX_ERROR
            message = "Syntax or structural error detected by Yosys."

        return ValidationResult(
            candidate_id=candidate.candidate_id, status=status, tool="symbiyosys",
            message=message, proof_depth=depth if status == AssertionStatus.PROVEN_FORMAL else None,
            counterexample=cex_text, error_log=output if status != AssertionStatus.PROVEN_FORMAL else "",
            runtime_sec=runtime
        )

    def validate(self, rtl_ctx: RTLContext, gated_candidates: List[CandidateAssertion], depth: int = 50) -> List[ValidationResult]:
        return [self._run_symbiyosys_native(rtl_ctx, cand, depth) for cand in gated_candidates]