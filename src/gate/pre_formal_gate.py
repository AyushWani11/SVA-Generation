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
import difflib
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

        # C1 — signal validity (exact + fuzzy fallback)
        sig_ok, bad_signals, corrections, corrected_text = self.check_signal_validity(
            candidate, rtl_ctx
        )
        if not sig_ok:
            return GateResult(
                candidate_id=candidate.candidate_id,
                accepted=False,
                reject_reason=f"Unknown signals (no fuzzy match): {', '.join(bad_signals)}",
                diagnostics={"bad_signals": bad_signals},
            )
        # Apply fuzzy corrections to the working text for downstream steps
        if corrections:
            candidate.assertion_text = corrected_text
            candidate.quality_flags.append(
                f"fuzzy_corrected:{','.join(f'{o}→{c}' for o, c in corrections.items())}"
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
            corrected_text=corrected_text if corrections else None,
            fuzzy_corrections=corrections,
        )

    # ── C1: signal validity ───────────────────────────────────────────

    # Minimum similarity ratio (0.0–1.0) for a fuzzy match to be accepted.
    FUZZY_CUTOFF = 0.70

    def check_signal_validity(
        self, candidate: CandidateAssertion, rtl_ctx: RTLContext
    ) -> Tuple[bool, List[str], Dict[str, str], str]:
        """
        Two-phase signal validity check.

        Phase 1 — exact match against known signal/parameter names.
        Phase 2 — for unknowns, fuzzy-match against the known dictionary
                   using difflib (stdlib).  If a single close match is found
                   at >= FUZZY_CUTOFF similarity the identifier is auto-corrected
                   in the returned text.

        Returns:
            (all_valid, still_unknown, corrections_map, corrected_text)
            • all_valid       — True if every identifier was resolved.
            • still_unknown   — identifiers that could not be resolved at all.
            • corrections_map — {original: corrected} for every fuzzy fix applied.
            • corrected_text  — assertion text with fuzzy corrections applied
                                (same as input when corrections_map is empty).
        """
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

        original_text = candidate.assertion_text

        # Strip comments and string literals before extracting identifiers
        code = original_text
        code = re.sub(r"//[^\n]*", "", code)
        code = re.sub(r'"[^"]*"', "", code)

        all_ids = set(re.findall(r"\b([a-zA-Z_]\w*)\b", code))
        non_kw = {
            i for i in all_ids
            if i not in sva_keywords
            and not i.startswith("$")
            and not i.startswith("p_")
        }

        known = set(rtl_ctx.signals.keys()) | set(rtl_ctx.parameters.keys())
        unknown = non_kw - known
        # Allow property-name identifiers
        unknown = {u for u in unknown if not (u.startswith("p_") or u.endswith("_prop"))}

        if not unknown:
            return True, [], {}, original_text

        # ── Phase 2: fuzzy matching ────────────────────────────────────
        known_list = sorted(known)          # stable ordering for difflib
        corrections: Dict[str, str] = {}
        still_unknown: List[str] = []

        for ident in sorted(unknown):
            matches = difflib.get_close_matches(
                ident, known_list,
                n=1,
                cutoff=self.FUZZY_CUTOFF,
            )
            if matches:
                corrections[ident] = matches[0]
            else:
                still_unknown.append(ident)

        if still_unknown:
            return False, still_unknown, corrections, original_text

        # All unknowns resolved — apply corrections to the assertion text
        corrected = original_text
        for original_id, fixed_id in corrections.items():
            # Replace whole-word occurrences only to avoid partial substitutions
            corrected = re.sub(
                rf"\b{re.escape(original_id)}\b", fixed_id, corrected
            )

        return True, [], corrections, corrected

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
