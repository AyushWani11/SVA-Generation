"""
VERIFY V2 — RTL Context Builder
================================
Wraps the existing V1 RTLParser and produces a normalized RTLContext.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rtl_parser import RTLParser, ModuleInfo
from core.models import RTLContext, ModuleSignal


class RTLContextBuilder:
    """Build an RTLContext from an RTL source file."""

    def __init__(self):
        self._parser = RTLParser()

    # ── public API ────────────────────────────────────────────────────

    def build(self, rtl_path: str) -> RTLContext:
        """Parse an RTL file and return a fully-populated RTLContext."""
        module_info: ModuleInfo = self._parser.parse_file(rtl_path)

        signals = {
            name: ModuleSignal(
                name=name,
                direction=sig.direction,
                width=sig.width,
                dtype="logic",
            )
            for name, sig in module_info.signals.items()
        }

        clk_candidates, rst_candidates = self.infer_clock_reset(
            signals, module_info.raw_code
        )

        fsm_state_names = [s.name for s in module_info.fsm_states]

        return RTLContext(
            module_name=module_info.name,
            rtl_path=rtl_path,
            raw_code=module_info.raw_code,
            signals=signals,
            parameters=module_info.parameters,
            fsm_states=fsm_state_names,
            clock_candidates=clk_candidates,
            reset_candidates=rst_candidates,
            dependency_groups=module_info.signal_groups,
        )

    # ── clock / reset inference ───────────────────────────────────────

    def infer_clock_reset(
        self, signals: Dict[str, ModuleSignal], rtl_code: str
    ) -> Tuple[List[str], List[str]]:
        """Heuristically identify clock and reset signals."""
        clk_patterns = [r"\bclk\b", r"\bclock\b", r"\bclk_i\b"]
        rst_patterns = [r"\brst_n\b", r"\brst\b", r"\breset\b", r"\brst_ni\b", r"\barst\b"]

        clocks: List[str] = []
        resets: List[str] = []

        for name in signals:
            for p in clk_patterns:
                if re.search(p, name, re.IGNORECASE):
                    clocks.append(name)
                    break
            for p in rst_patterns:
                if re.search(p, name, re.IGNORECASE):
                    resets.append(name)
                    break

        # Also check posedge/negedge usage in always blocks
        for m in re.finditer(r"@\s*\(\s*posedge\s+(\w+)", rtl_code):
            sig = m.group(1)
            if sig in signals and sig not in clocks:
                clocks.append(sig)

        return clocks, resets
