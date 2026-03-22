"""
VERIFY V2 — Pre-Formal Quality Gate
======================================
Cheap pre-filter that rejects low-quality candidates BEFORE
sending them to expensive formal tools.

Checks:
  C1. Signal validity — unknown signals are rejected.
  C2. Syntax shape     — basic structural parse (property/endproperty/assert).
  C3. Vacuity heuristics — tautologies, dead antecedents, duplicates.
  C4. Canonicalization + dedup via semantic hashing.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import CandidateAssertion, GateResult, RTLContext
from gate.canonicalizer import AssertionCanonicalizer


class PreFormalGate:
    """Evaluate candidates before formal verification."""

    def __init__(self):
        self._canon = AssertionCanonicalizer()
        self._seen_hashes: Set[str] = set()

    # ── public API ────────────────────────────────────────────────────

    def evaluate(
        self, candidate: CandidateAssertion, rtl_ctx: RTLContext
    ) -> GateResult:
        """Run all checks on a single candidate and return a GateResult."""
        diagnostics: Dict[str, Any] = {}

        # C1 — signal validity
        sig_ok, bad_signals = self.check_signal_validity(candidate, rtl_ctx)
        if not sig_ok:
            return GateResult(
                candidate_id=candidate.candidate_id,
                accepted=False,
                reject_reason=f"Unknown signals: {', '.join(bad_signals)}",
                diagnostics={"bad_signals": bad_signals},
            )

        # C2 — syntax shape
        syn_ok, syn_msg = self.check_syntax_shape(candidate.assertion_text)
        if not syn_ok:
            return GateResult(
                candidate_id=candidate.candidate_id,
                accepted=False,
                reject_reason=f"Syntax shape check failed: {syn_msg}",
                diagnostics={"syntax_issue": syn_msg},
            )

        # C3 — vacuity
        vac_ok, vac_msg = self.check_vacuity(candidate.assertion_text)
        diagnostics["vacuity_risk"] = 0.0 if vac_ok else 0.8
        if not vac_ok:
            return GateResult(
                candidate_id=candidate.candidate_id,
                accepted=False,
                reject_reason=f"Vacuity check failed: {vac_msg}",
                diagnostics=diagnostics,
            )

        # C4 — canonical dedup
        norm = self._canon.normalize(candidate.assertion_text)
        chash = self._canon.canonical_hash(norm)
        if chash in self._seen_hashes:
            return GateResult(
                candidate_id=candidate.candidate_id,
                accepted=False,
                reject_reason="Duplicate (canonical hash collision)",
                normalized_text=norm,
                canonical_hash=chash,
                diagnostics=diagnostics,
            )
        self._seen_hashes.add(chash)

        return GateResult(
            candidate_id=candidate.candidate_id,
            accepted=True,
            normalized_text=norm,
            canonical_hash=chash,
            diagnostics=diagnostics,
        )

    # ── C1: signal validity ───────────────────────────────────────────

    def check_signal_validity(
        self, candidate: CandidateAssertion, rtl_ctx: RTLContext
    ) -> Tuple[bool, List[str]]:
        """Check that all identifiers in the assertion are known signals or SVA keywords."""
        sva_keywords = {
            "property", "endproperty", "assert", "assume", "cover",
            "posedge", "negedge", "disable", "iff", "begin", "end",
            "if", "else", "case", "endcase", "for", "while",
            "logic", "bit", "int", "reg", "wire",
            "true", "false", "null",
            # SVA system functions / operators
            "past", "rose", "fell", "stable", "changed",
            "onehot", "onehot0", "countones", "isunknown", "bits",
            "error", "warning", "info", "fatal", "display",
            "s_eventually", "s_always", "s_until", "s_nexttime",
            # Common identifiers that aren't signals
            "P", "_P_",
        }

        # Strip comments and string literals before extracting identifiers
        code = candidate.assertion_text
        # Remove single-line comments
        code = re.sub(r"//[^\n]*", "", code)
        # Remove string literals inside $error("..."), $warning("..."), etc.
        code = re.sub(r'"[^"]*"', "", code)

        all_ids = set(re.findall(r"\b([a-zA-Z_]\w*)\b", code))
        # Remove SVA keywords and dollar-prefixed system tasks
        non_kw = {i for i in all_ids if i not in sva_keywords and not i.startswith("$") and not i.startswith("p_")}

        known = set(rtl_ctx.signals.keys()) | set(rtl_ctx.parameters.keys())
        unknown = non_kw - known
        # Allow property-name identifiers that start with p_ or end with _prop
        unknown = {u for u in unknown if not (u.startswith("p_") or u.endswith("_prop"))}

        if unknown:
            return False, sorted(unknown)
        return True, []

    # ── C2: syntax shape ─────────────────────────────────────────────

    def check_syntax_shape(self, assertion_text: str) -> Tuple[bool, str]:
        """Basic structural checks on the assertion text."""
        issues = []

        # Count standalone property declarations (exclude 'assert property', 'assume property', 'cover property')
        prop_declarations = len(re.findall(r"(?<!\w)\bproperty\s+\w+", assertion_text))
        endprop_count = len(re.findall(r"\bendproperty\b", assertion_text))
        if prop_declarations != endprop_count:
            issues.append(f"Mismatched property/endproperty ({prop_declarations}/{endprop_count})")

        if not re.search(r"\bassert\s+property\b", assertion_text):
            issues.append("Missing 'assert property'")

        if not re.search(r"@\s*\(\s*(?:posedge|negedge)\s+\w+\s*\)", assertion_text):
            issues.append("Missing clock edge specification")

        # Balanced parentheses
        depth = 0
        for ch in assertion_text:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth < 0:
                issues.append("Unbalanced parentheses")
                break
        if depth > 0:
            issues.append("Unclosed parentheses")

        if issues:
            return False, "; ".join(issues)
        return True, ""

    # ── C3: vacuity heuristics ───────────────────────────────────────

    def check_vacuity(self, assertion_text: str) -> Tuple[bool, str]:
        """Flag likely-vacuous assertions."""
        # Tautology: consequent is 1'b1 or duplicates antecedent
        if re.search(r"\|->\s*1\b", assertion_text) or re.search(r"\|=>\s*1\b", assertion_text):
            return False, "Consequent is always true (tautology)"

        # Both sides identical (after stripping whitespace)
        imp_match = re.search(r"(.+?)\s*\|->\s*(.+?)\s*;", assertion_text, re.DOTALL)
        if imp_match:
            lhs = re.sub(r"\s+", "", imp_match.group(1))
            rhs = re.sub(r"\s+", "", imp_match.group(2))
            if lhs == rhs:
                return False, "Antecedent equals consequent"

        return True, ""
