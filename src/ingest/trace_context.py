"""
VERIFY V2 — Trace Context Builder
===================================
Wraps the existing V1 InvariantMiner and produces a TraceContext.
Supports VCD loading or synthetic trace fallback.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invariant_miner import InvariantMiner
from core.models import RTLContext, TraceContext


class TraceContextBuilder:
    """Build a TraceContext (with mined invariants) from traces or synthetic simulation."""

    # ── public API ────────────────────────────────────────────────────

    def build(
        self,
        rtl_ctx: RTLContext,
        vcd_path: Optional[str] = None,
        cycles: int = 200,
    ) -> TraceContext:
        """
        Build a TraceContext.  If *vcd_path* is provided and the file exists,
        mine from VCD; otherwise fall back to synthetic traces.
        """
        signal_names = list(rtl_ctx.signals.keys())
        miner = InvariantMiner(signal_names=signal_names)

        if vcd_path and Path(vcd_path).exists():
            miner.load_vcd(vcd_path)
            source = "vcd"
        else:
            traces = miner.generate_synthetic_traces(
                rtl_ctx.module_name, rtl_ctx.raw_code, num_cycles=cycles
            )
            miner.load_traces_from_dict(traces)
            source = "synthetic"

        raw_invariants = miner.mine_all()

        inv_expressions: List[str] = []
        confidence_map: Dict[str, float] = {}
        for inv in raw_invariants:
            inv_expressions.append(inv.expression)
            confidence_map[inv.expression] = inv.confidence

        return TraceContext(
            source=source,
            cycles=len(miner.traces),
            signals_present=signal_names,
            mined_invariants=inv_expressions,
            invariant_confidence=confidence_map,
        )

    # ── utility (kept for parity with blueprint) ─────────────────────

    def mine_invariants(
        self, traces: List[Dict[str, int]], signals: List[str]
    ) -> Tuple[List[str], Dict[str, float]]:
        """Standalone helper: mine invariants from raw trace dicts."""
        miner = InvariantMiner(signal_names=signals)
        miner.load_traces_from_dict(traces)
        raw = miner.mine_all()
        exprs = [inv.expression for inv in raw]
        confs = {inv.expression: inv.confidence for inv in raw}
        return exprs, confs
