"""
VERIFY V2 — Multi-Strategy Candidate Generator
=================================================
Runs multiple generation strategies in sequence and collects the full
candidate pool with provenance tags.
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import (
    CandidateAssertion, IntentType,
    RTLContext, SpecContext, TraceContext,
)
from generate.prompt_engine import PromptEngine


class CandidateGenerator:
    """Generate CandidateAssertions via multiple LLM-backed strategies."""

    DEFAULT_STRATEGIES = [
        "spec_driven",
        "rtl_driven",
        "invariant_seeded",
        "holistic",
        "chiraag_generation",
    ]

    def __init__(self, llm, prompt_engine: Optional[PromptEngine] = None):
        self._llm = llm
        self._pe = prompt_engine or PromptEngine()

    def generate(
        self,
        rtl_ctx: RTLContext,
        spec_ctx: SpecContext,
        trace_ctx: TraceContext,
        strategies: Optional[List[str]] = None,
    ) -> List[CandidateAssertion]:
        """Run all requested strategies and return the combined candidate pool."""
        strategies = strategies or self.DEFAULT_STRATEGIES
        all_candidates: List[CandidateAssertion] = []

        signal_defs = self._format_signals(rtl_ctx, spec_ctx)
        spec_text = self._format_spec(spec_ctx)
        mined_text = self._format_invariants(trace_ctx)

        for strategy in strategies:
            payload = self._build_payload(
                strategy, rtl_ctx, spec_ctx, trace_ctx,
                signal_defs, spec_text, mined_text,
            )
            if payload is None:
                continue 

            candidates = self._run_strategy(strategy, payload, rtl_ctx)
            all_candidates.extend(candidates)

        return all_candidates

    def _run_strategy(
        self, strategy: str, payload: Dict[str, Any], rtl_ctx: RTLContext,
    ) -> List[CandidateAssertion]:
        """Render the prompt, call the LLM, and parse assertions."""
        prompt = self._pe.render(strategy, payload)
        prompt_id = self._pe.prompt_id(strategy, payload)

        response = self._llm.call(prompt, tag=strategy)

        # CRITICAL FIX: Look for 'raw_text' first!
        raw_text = getattr(response, "raw_text", getattr(response, "text", getattr(response, "content", str(response))))

        # If it still stringified the object, manually unescape the newlines
        if isinstance(raw_text, str):
            raw_text = raw_text.replace('\\n', '\n').replace('\\t', ' ')

        extracted_texts = self._extract_assertions(raw_text)

        if not extracted_texts and strategy not in ["chiraag_semantic_breakdown", "sangam_mapping"]:
            print(f"\n      [DEBUG] Strategy '{strategy}' extracted 0 assertions!")
            print(f"      [DEBUG] Raw LLM Output snippet:\n{raw_text[:500]}...\n")

        candidates: List[CandidateAssertion] = []
        for assertion_text in extracted_texts:
            cid = f"cand_{uuid.uuid4().hex[:8]}"
            prop_name = self._extract_property_name(assertion_text)
            intent_hint = self._guess_intent(assertion_text)
            used_signals = self._extract_used_signals(assertion_text, rtl_ctx)

            candidates.append(CandidateAssertion(
                candidate_id=cid,
                assertion_text=assertion_text,
                property_name=prop_name,
                intent_hint=intent_hint,
                source_strategy=strategy,
                source_prompt_id=prompt_id,
                used_signals=used_signals,
            ))

        return candidates

    def _build_payload(
        self,
        strategy: str,
        rtl_ctx: RTLContext,
        spec_ctx: SpecContext,
        trace_ctx: TraceContext,
        signal_defs: str,
        spec_text: str,
        mined_text: str,
    ) -> Optional[Dict[str, Any]]:
        design_name = spec_ctx.design_name or rtl_ctx.module_name
        description = spec_ctx.description or design_name

        if strategy == "spec_driven":
            return dict(
                design_name=design_name, description=description,
                rtl_code=rtl_ctx.raw_code, spec_text=spec_text,
                signal_defs=signal_defs,
            )
        if strategy == "rtl_driven":
            return dict(rtl_code=rtl_ctx.raw_code)
        if strategy == "invariant_seeded":
            return dict(
                design_name=design_name, description=description,
                rtl_code=rtl_ctx.raw_code, mined_invariants=mined_text,
            )
        if strategy == "holistic":
            return dict(
                design_name=design_name, description=description,
                rtl_code=rtl_ctx.raw_code, spec_text=spec_text,
                signal_defs=signal_defs, mined_invariants=mined_text,
            )
        if strategy == "chiraag_generation":
            return dict(
                design_name=design_name,
                rtl_code=rtl_ctx.raw_code,
                semantic_breakdown_json="[]",
            )
        return None

    def _extract_assertions(self, text: str) -> List[str]:
        # Fix hallucinated outer wrappers by the LLM
        text = re.sub(r'@\s*\(\s*posedge\s+clk\s*\)\s*assert\s+property', 'assert property', text, flags=re.IGNORECASE)

        pattern = re.compile(
            r'((?://[^\n]*\n\s*)*(?:\b\w+\s*:\s*)?\bassert\s+property\s*\([^;]+;)',
            re.DOTALL | re.IGNORECASE
        )
        matches = pattern.findall(text)
        
        cleaned_matches = []
        for m in matches:
            clean = m.replace('```systemverilog', '').replace('```', '').strip()
            if clean:
                cleaned_matches.append(clean)
                
        return cleaned_matches

    def _extract_used_signals(self, assertion_text: str, rtl_ctx: RTLContext) -> List[str]:
        found = []
        for name in rtl_ctx.signals:
            if re.search(rf"\b{re.escape(name)}\b", assertion_text):
                found.append(name)
        return sorted(set(found))

    @staticmethod
    def _extract_property_name(text: str) -> str:
        m_inline = re.search(r"(\w+)\s*:\s*assert\s+property", text)
        if m_inline:
            return m_inline.group(1)
        return "unnamed_prop"

    @staticmethod
    def _guess_intent(text: str) -> Optional[IntentType]:
        tag = re.search(r"//\s*\[(\w+)\]", text)
        if tag:
            try:
                return IntentType(tag.group(1).upper())
            except ValueError:
                pass
        return None

    @staticmethod
    def _format_signals(rtl_ctx: RTLContext, spec_ctx: SpecContext) -> str:
        lines = []
        for name, sig in sorted(rtl_ctx.signals.items()):
            desc = spec_ctx.signal_descriptions.get(name, "")
            w = f"[{sig.width}-bit]" if sig.width > 1 else "[1-bit]"
            lines.append(f"  {sig.direction:8s} {w:10s} {name}: {desc}")
        return "\n".join(lines)

    @staticmethod
    def _format_spec(spec_ctx: SpecContext) -> str:
        if not spec_ctx.clauses:
            return "No specification available."
        lines = []
        for c in spec_ctx.clauses:
            lines.append(f"[{c.intent.value}] {c.text}")
        return "\n".join(lines)

    @staticmethod
    def _format_invariants(trace_ctx: TraceContext) -> str:
        if not trace_ctx.mined_invariants:
            return "No invariants mined."
        lines = [f"=== Mined Invariants ({len(trace_ctx.mined_invariants)} total) ==="]
        for expr in trace_ctx.mined_invariants:
            conf = trace_ctx.invariant_confidence.get(expr, 0)
            lines.append(f"  - {expr}  (confidence: {conf*100:.0f}%)")
        return "\n".join(lines)