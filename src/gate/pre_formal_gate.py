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

        # C1 — signal validity
        sig_ok, bad_signals, fuzzy_fixes = self.check_signal_validity(candidate, rtl_ctx)
        
        # Apply fuzzy fixes if any
        if fuzzy_fixes:
            for bad_sig, good_sig in fuzzy_fixes.items():
                candidate.assertion_text = re.sub(rf"\b{bad_sig}\b", good_sig, candidate.assertion_text)
            diagnostics["fuzzy_corrections"] = fuzzy_fixes

        if not sig_ok:
            print(f"      [Gate] Rejected {candidate.candidate_id}: Unknown signals -> {bad_signals}")
            return GateResult(
                candidate_id=candidate.candidate_id,
                accepted=False,
                reject_reason=f"Unknown signals: {', '.join(bad_signals)}",
                diagnostics={"bad_signals": bad_signals},
            )

        # C2 — syntax shape
        syn_ok, syn_msg = self.check_syntax_shape(candidate.assertion_text)
        if not syn_ok:
            print(f"      [Gate] Rejected {candidate.candidate_id}: Syntax -> {syn_msg}")
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
            print(f"      [Gate] Rejected {candidate.candidate_id}: Vacuous -> {vac_msg}")
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

        # Return Success
        res = GateResult(
            candidate_id=candidate.candidate_id,
            accepted=True,
            normalized_text=norm,
            canonical_hash=chash,
            diagnostics=diagnostics,
        )
        
        try:
            res.fuzzy_corrections = fuzzy_fixes
        except Exception:
            pass
            
        return res

    # ── C1: signal validity ───────────────────────────────────────────

    def check_signal_validity(
        self, candidate: CandidateAssertion, rtl_ctx: RTLContext
    ) -> Tuple[bool, List[str], Dict[str, str]]:
        """Check that all identifiers in the assertion are known signals or SVA keywords."""
        sva_keywords = {
            "property", "endproperty", "assert", "assume", "cover",
            "posedge", "negedge", "edge", "disable", "iff", "begin", "end",
            "if", "else", "case", "endcase", "for", "while",
            "logic", "bit", "int", "reg", "wire", "assign", "always",
            "true", "false", "null", "sequence", "endsequence",
            "past", "rose", "fell", "stable", "changed",
            "onehot", "onehot0", "countones", "isunknown", "bits",
            "error", "warning", "info", "fatal", "display",
            "s_eventually", "s_always", "s_until", "s_nexttime",
            "eventually", "always", "until", "until_with", "nexttime",
            "implies", "intersect", "first_match", "throughout", "within",
            "weak", "strong", "sync_accept_on", "sync_reject_on", "accept_on", "reject_on",
            "not", "and", "or", "xor", "xnor", "nand", "nor"
        }

        code = candidate.assertion_text
        
        # 0. Fix escaped newlines/tabs from raw API strings
        code = code.replace('\\n', ' ').replace('\\t', ' ').replace('\\r', ' ')
        
        # 1. Remove comments
        code = re.sub(r"//[^\n]*", "", code)
        code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
        
        # 2. Remove strings
        code = re.sub(r'"[^"]*"', "", code)
        
        # 3. Strip Verilog numeric literals
        code = re.sub(r"\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+", "", code)
        code = re.sub(r"'[bBoOdDhH]?[0-9a-fA-F_xXzZ]+", "", code)
        code = re.sub(r"\b\d+\b", "", code)
        
        # 4. Strip out the inline assertion label
        code = re.sub(r'\b\w+\s*:\s*assert\b', 'assert', code)

        all_ids = set(re.findall(r"\b([a-zA-Z_]\w*)\b", code))
        non_kw = {i for i in all_ids if i not in sva_keywords and not i.startswith("$")}

        # Restore label fallback filter
        non_kw = {u for u in non_kw if not (u.startswith("p_") or u.endswith("_prop") or u.startswith("assert_"))}
        
        # 5. Ignore single-letter phantom variables (loop counters, regex remnants like '\n')
        non_kw = {u for u in non_kw if len(u) > 1}

        known = set(rtl_ctx.signals.keys()) | set(rtl_ctx.parameters.keys())
        unknown = non_kw - known

        fuzzy_fixes = {}
        unfixable = []
        known_list = list(known)

        # Smart fallbacks for common template mismatches
        common_maps = {
            "clk": [s for s in known_list if "clk" in s.lower() or "clock" in s.lower()],
            "rst_n": [s for s in known_list if "rst" in s.lower() or "reset" in s.lower()],
            "rst": [s for s in known_list if "rst" in s.lower() or "reset" in s.lower()]
        }

        for u in unknown:
            if not u: 
                continue
            
            # Check common mappings first
            if u in common_maps and common_maps[u]:
                fuzzy_fixes[u] = common_maps[u][0]
                continue
                
            # Then check fuzzy string matching
            matches = difflib.get_close_matches(u, known_list, n=1, cutoff=0.75)
            if matches:
                fuzzy_fixes[u] = matches[0]
            else:
                unfixable.append(u)

        if unfixable:
            return False, sorted(unfixable), fuzzy_fixes

        return True, [], fuzzy_fixes

    # ── C2: syntax shape ─────────────────────────────────────────────

    def check_syntax_shape(self, assertion_text: str) -> Tuple[bool, str]:
        """Basic structural checks on the assertion text."""
        issues = []
        
        code = assertion_text.replace('\\n', '\n')
        code = re.sub(r"//[^\n]*", "", code)
        code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
        code = re.sub(r'"[^"]*"', "", code)

        if not re.search(r"\bassert\s+property\b", code):
            issues.append("Missing 'assert property'")

        if not re.search(r"@\s*\(\s*(?:posedge|negedge|edge)\s+\w+\s*\)", code):
            issues.append("Missing clock edge specification")

        depth = 0
        for ch in code:
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
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
        code = assertion_text.replace('\\n', ' ')
        code = re.sub(r"//[^\n]*", "", code)
        code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)

        if re.search(r"\|->\s*1\b", code) or re.search(r"\|=>\s*1\b", code):
            return False, "Consequent is always true (tautology)"

        imp_match = re.search(r"(.+?)\s*\|->\s*(.+)", code, re.DOTALL)
        if imp_match:
            lhs = re.sub(r"\s+", "", imp_match.group(1))
            rhs = re.sub(r"\s+", "", imp_match.group(2))
            rhs = rhs.rstrip(';').rstrip(')').replace('else$error', '')
            if lhs == rhs:
                return False, "Antecedent equals consequent"

        return True, ""