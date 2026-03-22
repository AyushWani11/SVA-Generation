"""
VERIFY V2 — Assertion Canonicalizer
=====================================
Normalizes assertion text and computes semantic hashes for dedup.
"""

import hashlib
import re


class AssertionCanonicalizer:
    """Normalize assertions and produce canonical hashes."""

    def normalize(self, assertion_text: str) -> str:
        """Strip comments, collapse whitespace, lowercase identifiers
        that are NOT signal names (property names, etc.)."""
        lines = []
        for line in assertion_text.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("//"):
                lines.append(stripped)
        text = " ".join(lines)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Normalize property names to a placeholder for structural comparison
        text = re.sub(r"property\s+\w+", "property _P_", text)
        text = re.sub(
            r"assert\s+property\s*\(\s*\w+\s*\)",
            "assert property (_P_)",
            text,
        )
        # Remove $error messages (don't affect semantics)
        text = re.sub(r"\s*else\s+\$error\([^)]*\)\s*;?", ";", text)
        return text

    def canonical_hash(self, normalized_text: str) -> str:
        """SHA-256 of the normalized text (first 16 hex chars)."""
        return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16]
