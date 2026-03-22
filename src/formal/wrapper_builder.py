"""
VERIFY V2 — Wrapper Builder
==============================
Generates a SystemVerilog wrapper that binds assertions to the DUT.
"""

from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import RTLContext


class WrapperBuilder:
    """Build a SystemVerilog wrapper with assertion(s) bound to the DUT."""

    def build_bound_wrapper(
        self,
        rtl_ctx: RTLContext,
        assertion_text: str,
        top_module: Optional[str] = None,
    ) -> str:
        """Return a wrapper SV string containing the assertion bound to the design."""
        module = top_module or rtl_ctx.module_name

        # Build port connection list for bind
        port_conns = []
        for name, sig in sorted(rtl_ctx.signals.items()):
            if sig.direction in ("input", "output"):
                port_conns.append(f"    .{name}({name})")

        port_str = ",\n".join(port_conns)

        return f"""\
// Auto-generated assertion wrapper — VERIFY V2
// DUT: {module}  RTL: {rtl_ctx.rtl_path}

module assertion_checker (
{self._port_declarations(rtl_ctx)}
);

{assertion_text}

endmodule

// Bind the checker to the DUT
// bind {module} assertion_checker u_checker (
// {port_str}
// );
"""

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _port_declarations(rtl_ctx: RTLContext) -> str:
        lines = []
        for name, sig in sorted(rtl_ctx.signals.items()):
            if sig.direction in ("input", "output"):
                width = f"[{sig.width-1}:0] " if sig.width > 1 else ""
                lines.append(f"    input logic {width}{name}")
        return ",\n".join(lines)
