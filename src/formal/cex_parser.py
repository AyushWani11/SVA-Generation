"""
VERIFY V2 — Counter-Example Parser
====================================
Extracts and minimises CEX traces from formal tool output.
"""

import re
from typing import Dict, List, Optional


class CexParser:
    """Parse counterexample traces from formal verification output."""

    def parse(self, output: str, assertion_name: str) -> Optional[str]:
        """Extract a human-readable counterexample trace from tool output."""
        lines = output.split("\n")
        cex_lines: List[str] = []
        capturing = False

        for line in lines:
            lower = line.lower()
            if "counterexample" in lower or "trace" in lower or "FAIL" in line:
                capturing = True
            if capturing:
                cex_lines.append(line)
            if capturing and line.strip() == "":
                capturing = False

        if cex_lines:
            return "\n".join(cex_lines)

        # Fallback
        return f"Counterexample for {assertion_name}. Full output:\n{output[:800]}"

    def minimise(self, cex_text: str) -> str:
        """Trim the CEX to the most relevant signal transitions."""
        # Keep only lines that contain signal assignments or time stamps
        relevant = []
        for line in cex_text.split("\n"):
            if re.search(r"(#\d+|=\s*[01xXzZ]|\btime\b|\bstep\b)", line, re.IGNORECASE):
                relevant.append(line)
        return "\n".join(relevant) if relevant else cex_text
