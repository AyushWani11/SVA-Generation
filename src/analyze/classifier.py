"""
VERIFY V2 — Assertion Classifier
===================================
Maps assertion text to an IntentType category.
"""

import re

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import IntentType


class AssertionClassifier:
    """Classify an assertion into an IntentType."""

    _RULES = {
        IntentType.RESET: [
            r"!rst_n\b", r"rst_ni\b", r"!rst\b", r"\breset\b",
        ],
        IntentType.SAFETY: [
            r"\b(?:full|empty)\b.*\|->.*!",
            r"!\(.*&&.*\)",
            r"<=.*MAX|>=.*MIN",
        ],
        IntentType.LIVENESS: [
            r"s_eventually\b",
            r"\#\#\[.*:\$\]",
            r"\[\*\]",
        ],
        IntentType.TIMING: [
            r"\#\#\d+",
            r"\#\#\[\d+:\d+\]",
            r"\$past\(",
        ],
    }

    def classify(self, assertion_text: str) -> IntentType:
        """Return the best-fit IntentType for *assertion_text*."""
        # Explicit comment tag takes precedence
        tag = re.search(r"//\s*\[(\w+)\]", assertion_text)
        if tag:
            try:
                return IntentType(tag.group(1).upper())
            except ValueError:
                pass

        for intent, patterns in self._RULES.items():
            for p in patterns:
                if re.search(p, assertion_text, re.IGNORECASE):
                    return intent

        return IntentType.INVARIANT
