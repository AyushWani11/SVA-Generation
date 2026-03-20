"""
VERIFY Framework: Main Orchestrator
=====================================================
Verification-Embedded Refinement with Iterative Feedback Yielding

This is the main entry point that orchestrates all 4 stages of the VERIFY pipeline:
  Stage 1: Specification Decomposition & Invariant Mining
  Stage 2: Multi-Strategy Assertion Generation
  Stage 3: Formal-in-the-Loop Validation & Refinement
  Stage 4: Analysis & Redundancy Elimination
"""

import os
import sys
import json
import argparse
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from rtl_parser import RTLParser, ModuleInfo
from llm_interface import LLMInterface, LLMResponse, AssertionExtractor
from invariant_miner import InvariantMiner
from formal_verifier import FormalVerifier, AssertionAnalyzer, VerificationResult

# Add prompts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "prompts"))
from templates import (
    SPEC_DRIVEN_GENERATION,
    RTL_DRIVEN_GENERATION,
    INVARIANT_SEEDED_GENERATION,
    COUNTEREXAMPLE_ANALYSIS,
    SYNTAX_CORRECTION,
    ASSERTION_CLASSIFICATION,
    REDUNDANCY_ANALYSIS,
    HOLISTIC_GENERATION,
    SANGAM_MAPPING,
    CHIRAAG_SEMANTIC_BREAKDOWN,
    CHIRAAG_CONTEXT_GENERATION,
)


class VERIFYOrchestrator:
    """Main orchestrator for the VERIFY framework pipeline."""
    
    def __init__(self, 
                 rtl_path: str,
                 spec_path: str = "",
                 design_key: str = "",
                 llm_provider: str = "openai",
                 llm_model: str = "gpt-4o",
                 api_key: str = "",
                 output_dir: str = "output",
                 max_refinement_iterations: int = 3):
        """
        Initialize the VERIFY orchestrator.
        
        Args:
            rtl_path: Path to the RTL design file (.sv/.v)
            spec_path: Path to the design specification JSON file
            design_key: Key in the spec JSON (e.g., 'fifo', 'arbiter')
            llm_provider: LLM provider ('openai', 'deepseek', 'local')
            llm_model: LLM model name
            api_key: API key for the LLM provider
            output_dir: Base output directory
            max_refinement_iterations: Max CEX-driven refinement loops
        """
        self.rtl_path = Path(rtl_path)
        self.spec_path = Path(spec_path) if spec_path else None
        self.design_key = design_key
        self.output_dir = Path(output_dir)
        self.max_iterations = min(max_refinement_iterations, 1)  # LAAG-RV: Exactly one repair attempt
        
        # Create output directories
        (self.output_dir / "assertions").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "logs").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "reports").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "formal").mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.parser = RTLParser()
        self.llm = LLMInterface(
            provider=llm_provider, model=llm_model, api_key=api_key,
            log_dir=str(self.output_dir / "logs")
        )
        self.miner = InvariantMiner()
        self.verifier = FormalVerifier(work_dir=str(self.output_dir / "formal"))
        
        # State
        self.module_info: Optional[ModuleInfo] = None
        self.spec_data: Dict = {}
        self.signal_map: Dict = {}
        self.semantic_breakdown: List[Dict] = []
        self.raw_assertions: List[str] = []
        self.verified_assertions: List[str] = []
        self.verification_results: List[VerificationResult] = []
        self.classification: Dict[str, str] = {}
        self.usefulness_scores: Dict[str, float] = {}
        self.redundancies: List[Tuple[int, int, str]] = []
        self.run_log: List[str] = []
        
    def run(self) -> Dict:
        """Execute the full VERIFY pipeline and return results."""
        self._log("=" * 60)
        self._log("VERIFY Framework - Starting Pipeline")
        self._log(f"Design: {self.rtl_path.name}")
        self._log(f"Time: {datetime.now().isoformat()}")
        self._log("=" * 60)
        
        # Display tool status
        self._log(self.verifier.get_tool_status())
        self._log("")
        
        start_time = time.time()
        
        # Stage 1: Specification Decomposition & Invariant Mining
        self._log("\n" + "=" * 40)
        self._log("STAGE 1: Specification Decomposition & Invariant Mining")
        self._log("=" * 40)
        self._stage1_spec_decomposition()
        
        # Stage 2: Multi-Strategy Assertion Generation
        self._log("\n" + "=" * 40)
        self._log("STAGE 2: Multi-Strategy Assertion Generation")
        self._log("=" * 40)
        self._stage2_multi_strategy_generation()
        
        # Stage 3: Formal-in-the-Loop Validation & Refinement
        self._log("\n" + "=" * 40)
        self._log("STAGE 3: Formal-in-the-Loop Validation & Refinement")
        self._log("=" * 40)
        self._stage3_formal_validation()
        
        # Stage 4: Analysis & Redundancy Elimination
        self._log("\n" + "=" * 40)
        self._log("STAGE 4: Analysis & Redundancy Elimination")
        self._log("=" * 40)
        self._stage4_analysis()
        
        elapsed = time.time() - start_time
        
        # Generate final report
        report = self._generate_report(elapsed)
        
        # Save outputs
        self._save_outputs(report)
        
        self._log(f"\nPipeline completed in {elapsed:.1f} seconds")
        self._log(f"Results saved to: {self.output_dir}")
        
        return report
    
    # ==========================================
    # STAGE 1: Specification Decomposition
    # ==========================================
    
    def _stage1_spec_decomposition(self):
        """Stage 1: Parse RTL, load spec, mine invariants."""
        
        # 1a. Parse RTL
        self._log("\n[1a] Parsing RTL design...")
        self.module_info = self.parser.parse_file(str(self.rtl_path))
        self._log(f"  Module: {self.module_info.name}")
        self._log(f"  Signals: {len(self.module_info.signals)}")
        self._log(f"  FSM States: {len(self.module_info.fsm_states)}")
        self._log(f"  Signal Groups: {len(self.module_info.signal_groups)}")
        for i, group in enumerate(self.module_info.signal_groups):
            self._log(f"    Group {i+1}: {', '.join(group)}")
        
        # 1b. Load specification
        self._log("\n[1b] Loading design specification...")
        if self.spec_path and self.spec_path.exists():
            with open(self.spec_path, 'r') as f:
                all_specs = json.load(f)
            
            if self.design_key and self.design_key in all_specs:
                self.spec_data = all_specs[self.design_key]
            else:
                # Try to match by module name
                for key, spec in all_specs.items():
                    if key.lower() in self.module_info.name.lower():
                        self.spec_data = spec
                        self.design_key = key
                        break
            
            if self.spec_data:
                self._log(f"  Loaded spec for: {self.spec_data.get('name', self.design_key)}")
            else:
                self._log("  WARNING: No matching specification found")
        else:
            self._log("  No specification file provided - using RTL-only mode")
        
        # 1c. Dynamic Invariant Mining
        self._log("\n[1c] Mining dynamic invariants from simulation traces...")
        signal_names = list(self.module_info.signals.keys())
        self.miner = InvariantMiner(signal_names=signal_names)
        
        # Generate synthetic traces (in real use, load VCD from simulation)
        traces = self.miner.generate_synthetic_traces(
            self.module_info.name, self.module_info.raw_code, num_cycles=200
        )
        self.miner.load_traces_from_dict(traces)
        
        # Mine invariants
        invariants = self.miner.mine_all()
        self._log(f"  Mined {len(invariants)} candidate invariants:")
        categories = {}
        for inv in invariants:
            categories.setdefault(inv.category, []).append(inv)
        for cat, invs in sorted(categories.items()):
            self._log(f"    {cat}: {len(invs)} invariants")
            
        # 1d. Semantic Contextualization (SANGAM + ChIRAAG)
        self._log("\n[1d] Semantic Contextualization (SANGAM + ChIRAAG)...")
        if self.spec_data and self.module_info:
            spec_text = self._format_spec_for_prompt()
            signal_defs = self._format_signals_for_prompt()
            
            # SANGAM Mapping
            self._log("  Running SANGAM Signal Mapping...")
            sangam_prompt = SANGAM_MAPPING.format(
                design_name=self.module_info.name,
                description=self.spec_data.get("description", self.module_info.name),
                rtl_code=self.module_info.raw_code,
                signal_defs=signal_defs,
                spec_text=spec_text
            )
            sangam_resp = self.llm.call(sangam_prompt, tag="sangam_mapping")
            try:
                # Extract JSON block
                json_str = sangam_resp.raw_text
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                self.signal_map = json.loads(json_str)
                self._log(f"  Mapped {len(self.signal_map)} signals")
            except Exception as e:
                self._log(f"  Warning: Failed to parse SANGAM mapping JSON: {e}")
                self.signal_map = {}

            # ChIRAAG Breakdown
            self._log("  Running ChIRAAG Semantic Breakdown...")
            chiraag_prompt = CHIRAAG_SEMANTIC_BREAKDOWN.format(
                spec_text=spec_text,
                signal_map_json=json.dumps(self.signal_map, indent=2)
            )
            chiraag_resp = self.llm.call(chiraag_prompt, tag="chiraag_breakdown")
            try:
                json_str = chiraag_resp.raw_text
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                self.semantic_breakdown = json.loads(json_str)
                self._log(f"  Extracted {len(self.semantic_breakdown)} semantic rules")
            except Exception as e:
                self._log(f"  Warning: Failed to parse ChIRAAG breakdown JSON: {e}")
                self.semantic_breakdown = []
        else:
            self._log("  Skipping semantic contextualization (no spec or RTL info)")
    
    # ==========================================
    # STAGE 2: Multi-Strategy Generation
    # ==========================================
    
    def _stage2_multi_strategy_generation(self):
        """Stage 2: Generate assertions using three complementary strategies."""
        
        rtl_code = self.module_info.raw_code
        spec_text = self._format_spec_for_prompt()
        signal_defs = self._format_signals_for_prompt()
        design_name = self.spec_data.get("name", self.module_info.name)
        description = self.spec_data.get("description", design_name)
        
        all_assertions = []
        
        # Strategy 1: Specification-Driven Generation
        self._log("\n[2a] Strategy 1: Specification-Driven Generation...")
        prompt_spec = SPEC_DRIVEN_GENERATION.format(
            design_name=design_name,
            description=description,
            rtl_code=rtl_code,
            spec_text=spec_text,
            signal_defs=signal_defs
        )
        
        response_spec = self.llm.call(prompt_spec, tag="spec_driven")
        self._log(f"  Generated {len(response_spec.assertions)} assertions")
        all_assertions.extend(response_spec.assertions)
        
        # Strategy 2: RTL-Driven Generation
        self._log("\n[2b] Strategy 2: RTL-Driven Generation...")
        prompt_rtl = RTL_DRIVEN_GENERATION.format(rtl_code=rtl_code)
        
        response_rtl = self.llm.call(prompt_rtl, tag="rtl_driven")
        self._log(f"  Generated {len(response_rtl.assertions)} assertions")
        all_assertions.extend(response_rtl.assertions)
        
        # Strategy 3: Invariant-Seeded Generation
        self._log("\n[2c] Strategy 3: Invariant-Seeded Generation...")
        mined_text = self.miner.to_text()
        prompt_inv = INVARIANT_SEEDED_GENERATION.format(
            design_name=design_name,
            description=description,
            rtl_code=rtl_code,
            mined_invariants=mined_text
        )
        
        response_inv = self.llm.call(prompt_inv, tag="invariant_seeded")
        self._log(f"  Generated {len(response_inv.assertions)} assertions")
        all_assertions.extend(response_inv.assertions)
        
        # Strategy 4: Holistic Generation
        self._log("\n[2d] Strategy 4: Holistic Generation...")
        prompt_holistic = HOLISTIC_GENERATION.format(
            design_name=design_name,
            description=description,
            rtl_code=rtl_code,
            spec_text=spec_text,
            signal_defs=signal_defs,
            mined_invariants=mined_text
        )
        
        response_holistic = self.llm.call(prompt_holistic, tag="holistic_driven")
        self._log(f"  Generated {len(response_holistic.assertions)} assertions")
        all_assertions.extend(response_holistic.assertions)
        
        # Strategy 5: ChIRAAG Context-Injected Generation
        if self.semantic_breakdown:
            self._log("\n[2e] Strategy 5: ChIRAAG Context-Injected Generation...")
            chiraag_gen_prompt = CHIRAAG_CONTEXT_GENERATION.format(
                design_name=design_name,
                rtl_code=rtl_code,
                semantic_breakdown_json=json.dumps(self.semantic_breakdown, indent=2)
            )
            
            response_chiraag = self.llm.call(chiraag_gen_prompt, tag="chiraag_generation")
            self._log(f"  Generated {len(response_chiraag.assertions)} assertions")
            all_assertions.extend(response_chiraag.assertions)
        
        # Deduplicate
        self.raw_assertions = self._deduplicate_assertions(all_assertions)
        self._log(f"\n  Total unique raw assertions: {len(self.raw_assertions)}")
    
    # ==========================================
    # STAGE 3: Formal Validation & Refinement
    # ==========================================
    
    def _stage3_formal_validation(self):
        """Stage 3: Counterexample-driven formal validation and refinement loop."""
        
        assertions_to_verify = list(self.raw_assertions)
        verified = []
        failed = []
        
        for iteration in range(self.max_iterations + 1):
            if not assertions_to_verify:
                break
            
            self._log(f"\n[3] Validation iteration {iteration + 1}...")
            self._log(f"  Assertions to verify: {len(assertions_to_verify)}")
            
            # Verify all current assertions
            results = self.verifier.verify_assertions(
                str(self.rtl_path), assertions_to_verify, self.module_info.name
            )
            
            new_to_verify = []
            
            for result in results:
                if result.status == "PROVEN":
                    verified.append(result.assertion_code)
                    self._log(f"  ✓ PROVEN: {result.assertion_name}")
                    
                elif result.status == "SYNTAX_ERROR" and iteration < self.max_iterations:
                    # Try to fix syntax errors via LLM
                    self._log(f"  ✗ SYNTAX ERROR: {result.assertion_name}")
                    signal_names = ", ".join(self.module_info.signals.keys())
                    
                    fix_prompt = SYNTAX_CORRECTION.format(
                        assertion_code=result.assertion_code,
                        error_messages=result.error_log,
                        signal_names=signal_names
                    )
                    fix_response = self.llm.call(fix_prompt, tag=f"syntax_fix_{result.assertion_name}")
                    
                    if fix_response.assertions:
                        new_to_verify.extend(fix_response.assertions)
                        self._log(f"    → LLM proposed {len(fix_response.assertions)} fixes")
                    else:
                        failed.append(result)
                        self._log(f"    → LLM could not fix, discarding")
                    
                elif result.status == "COUNTEREXAMPLE" and iteration < self.max_iterations:
                    # Feed counterexample to LLM for analysis
                    self._log(f"  ✗ COUNTEREXAMPLE: {result.assertion_name}")
                    
                    cex_prompt = COUNTEREXAMPLE_ANALYSIS.format(
                        design_name=self.module_info.name,
                        assertion_code=result.assertion_code,
                        counterexample_trace=result.counterexample or "No trace available",
                        spec_excerpt=self._format_spec_for_prompt()[:500],
                        rtl_excerpt=self.module_info.raw_code[:500]
                    )
                    cex_response = self.llm.call(cex_prompt, tag=f"cex_analysis_{result.assertion_name}")
                    
                    # Parse LLM's verdict
                    if "ASSERTION_WRONG" in cex_response.raw_text:
                        if cex_response.assertions:
                            new_to_verify.extend(cex_response.assertions)
                            self._log(f"    → LLM refined assertion, re-verifying")
                        else:
                            failed.append(result)
                            self._log(f"    → LLM identified wrong assertion but no fix, discarding")
                    elif "DESIGN_BUG" in cex_response.raw_text:
                        verified.append(result.assertion_code)  # The assertion is correct!
                        self._log(f"    → LLM identified potential DESIGN BUG!")
                        result.message = "POTENTIAL_DESIGN_BUG: " + result.message
                    else:
                        failed.append(result)
                        self._log(f"    → Analysis inconclusive, discarding")
                else:
                    failed.append(result)
                    if result.status == "SYNTAX_ERROR":
                        self._log(f"  ✗ SYNTAX ERROR (unfixable): {result.assertion_name}")
                    elif result.status == "COUNTEREXAMPLE":
                        self._log(f"  ✗ COUNTEREXAMPLE (max iterations): {result.assertion_name}")
                    else:
                        self._log(f"  ? {result.status}: {result.assertion_name}")
            
            assertions_to_verify = new_to_verify
        
        self.verified_assertions = verified
        self.verification_results = [
            VerificationResult(
                assertion_name=f"verified_{i}",
                assertion_code=a,
                status="PROVEN"
            )
            for i, a in enumerate(verified)
        ]
        
        self._log(f"\n  Final verified assertions: {len(self.verified_assertions)}")
        self._log(f"  Failed/discarded: {len(failed)}")
    
    # ==========================================
    # STAGE 4: Analysis & Redundancy Elimination
    # ==========================================
    
    def _stage4_analysis(self):
        """Stage 4: Classify, detect redundancy, and score usefulness."""
        
        if not self.verified_assertions:
            self._log("  No verified assertions to analyze.")
            return
        
        # 4a. Classification
        self._log("\n[4a] Classifying assertions...")
        for i, assertion in enumerate(self.verified_assertions):
            category = AssertionAnalyzer.classify_assertion(assertion)
            self.classification[f"verified_{i}"] = category
        
        cat_counts = {}
        for cat in self.classification.values():
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        for cat, count in sorted(cat_counts.items()):
            self._log(f"  {cat}: {count} assertions")
        
        # 4b. Redundancy Detection
        self._log("\n[4b] Detecting redundancies...")
        self.redundancies = AssertionAnalyzer.check_redundancy_simple(self.verified_assertions)
        self._log(f"  Found {len(self.redundancies)} potential redundancies")
        
        # Also try LLM-based redundancy analysis if >1 assertion
        if len(self.verified_assertions) > 1:
            assertions_text = "\n\n".join(
                f"[{i}] {a}" for i, a in enumerate(self.verified_assertions)
            )
            redundancy_prompt = REDUNDANCY_ANALYSIS.format(assertions=assertions_text)
            redundancy_response = self.llm.call(redundancy_prompt, tag="redundancy_analysis")
            self._log(f"  LLM redundancy analysis complete")
        
        # 4c. Usefulness Scoring
        self._log("\n[4c] Scoring usefulness...")
        for i, assertion in enumerate(self.verified_assertions):
            key = f"verified_{i}"
            cat = self.classification.get(key, "INVARIANT")
            score = AssertionAnalyzer.score_usefulness(assertion, cat, is_proven=True)
            self.usefulness_scores[key] = score
        
        # Summary
        avg_score = sum(self.usefulness_scores.values()) / len(self.usefulness_scores)
        self._log(f"  Average usefulness score: {avg_score:.2f}")
        
        # Identify non-redundant set
        redundant_indices = set()
        for _, idx_b, _ in self.redundancies:
            redundant_indices.add(idx_b)
        
        non_redundant = [
            a for i, a in enumerate(self.verified_assertions)
            if i not in redundant_indices
        ]
        self._log(f"\n  Non-redundant assertions: {len(non_redundant)}")
    
    # ==========================================
    # Report Generation & Output
    # ==========================================
    
    def _generate_report(self, elapsed: float) -> Dict:
        """Generate the final analysis report."""
        report = {
            "metadata": {
                "design": self.module_info.name if self.module_info else "",
                "rtl_file": str(self.rtl_path),
                "timestamp": datetime.now().isoformat(),
                "elapsed_seconds": round(elapsed, 2),
                "llm_stats": self.llm.get_stats(),
                "tool_status": {k: v for k, v in self.verifier.tool_available.items()}
            },
            "stage1_spec_processing": {
                "signals_count": len(self.module_info.signals) if self.module_info else 0,
                "signal_groups_count": len(self.module_info.signal_groups) if self.module_info else 0,
                "fsm_states_count": len(self.module_info.fsm_states) if self.module_info else 0,
                "mined_invariants_count": len(self.miner.invariants),
                "spec_available": bool(self.spec_data),
            },
            "stage2_generation": {
                "raw_assertions_count": len(self.raw_assertions),
            },
            "stage3_validation": {
                "verified_count": len(self.verified_assertions),
                "total_checked": len(self.raw_assertions),
                "success_rate": (len(self.verified_assertions) / max(len(self.raw_assertions), 1)) * 100,
            },
            "stage4_analysis": {
                "classification": dict(sorted(
                    {cat: list(self.classification.values()).count(cat) 
                     for cat in set(self.classification.values())}.items()
                )) if self.classification else {},
                "redundancies_found": len(self.redundancies),
                "non_redundant_count": len(self.verified_assertions) - len(
                    set(idx_b for _, idx_b, _ in self.redundancies)
                ),
                "avg_usefulness_score": round(
                    sum(self.usefulness_scores.values()) / max(len(self.usefulness_scores), 1), 3
                ),
            },
            "assertions": {
                "raw": self.raw_assertions,
                "verified": self.verified_assertions,
                "classifications": self.classification,
                "usefulness_scores": self.usefulness_scores,
            }
        }
        
        return report
    
    def _save_outputs(self, report: Dict):
        """Save all outputs to disk."""
        design_name = self.module_info.name if self.module_info else "unknown"
        
        # Save final assertion SVA file
        sva_path = self.output_dir / "assertions" / f"{design_name}_assertions.sv"
        with open(sva_path, 'w', encoding='utf-8') as f:
            f.write(f"// VERIFY Framework - Generated Assertions\n")
            f.write(f"// Design: {design_name}\n")
            f.write(f"// Generated: {datetime.now().isoformat()}\n")
            f.write(f"// Total Verified Assertions: {len(self.verified_assertions)}\n\n")
            
            for i, assertion in enumerate(self.verified_assertions):
                cat = self.classification.get(f"verified_{i}", "?")
                score = self.usefulness_scores.get(f"verified_{i}", 0)
                f.write(f"\n// === Assertion {i+1} [{cat}] (usefulness: {score:.2f}) ===\n")
                f.write(assertion + "\n")
        
        # Save JSON report
        report_path = self.output_dir / "reports" / f"{design_name}_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save run log
        log_path = self.output_dir / "logs" / f"{design_name}_pipeline.log"
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(self.run_log))
        
        # Save raw assertions (before validation)
        raw_path = self.output_dir / "assertions" / f"{design_name}_raw_assertions.sv"
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(f"// VERIFY Framework - Raw Generated Assertions (before validation)\n")
            f.write(f"// Design: {design_name}\n\n")
            for i, a in enumerate(self.raw_assertions):
                f.write(f"\n// --- Raw Assertion {i+1} ---\n")
                f.write(a + "\n")
        
        self._log(f"\nOutputs saved:")
        self._log(f"  Assertions: {sva_path}")
        self._log(f"  Raw assertions: {raw_path}")
        self._log(f"  Report: {report_path}")
        self._log(f"  Pipeline log: {log_path}")
    
    # ==========================================
    # Utility Methods
    # ==========================================
    
    def _format_spec_for_prompt(self) -> str:
        """Format the design specification for inclusion in prompts."""
        if not self.spec_data:
            return "No specification available. Generate assertions based on RTL analysis only."
        
        lines = []
        for key in ['functionality', 'reset_behavior', 'timing_constraints', 'safety_properties']:
            if key in self.spec_data:
                lines.append(f"\n### {key.replace('_', ' ').title()}:")
                if isinstance(self.spec_data[key], list):
                    for item in self.spec_data[key]:
                        lines.append(f"  - {item}")
                else:
                    lines.append(f"  {self.spec_data[key]}")
        
        return "\n".join(lines)
    
    def _format_signals_for_prompt(self) -> str:
        """Format signal definitions for inclusion in prompts."""
        if not self.module_info:
            return ""
        
        lines = []
        for name, sig in sorted(self.module_info.signals.items()):
            desc = self.spec_data.get("signals", {}).get(name, "")
            width_str = f"[{sig.width}-bit]" if sig.width > 1 else "[1-bit]"
            lines.append(f"  {sig.direction:8s} {width_str:10s} {name}: {desc}")
        
        return "\n".join(lines)
    
    def _deduplicate_assertions(self, assertions: List[str]) -> List[str]:
        """Remove duplicate assertions based on normalized text comparison."""
        seen = set()
        unique = []
        
        for a in assertions:
            # 1. Filter out comments first
            lines = []
            for line in a.split('\n'):
                stripped = line.strip()
                if stripped and not stripped.startswith('//'):
                    lines.append(stripped)
            
            # 2. Normalize whitespace for logic comparison
            normalized = " ".join(" ".join(lines).split()).lower()
            
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(a)
        
        return unique
    
    def _log(self, message: str):
        """Log a message to both console and run log."""
        print(message)
        self.run_log.append(message)


def main():
    """CLI entry point for the VERIFY framework."""
    parser = argparse.ArgumentParser(
        description="VERIFY: Verification-Embedded Refinement with Iterative Feedback Yielding",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run on FIFO design with specification
  python verify.py --rtl rtl/fifo.sv --spec prompts/design_specs.json --design fifo

  # Run on arbiter (RTL-only mode)
  python verify.py --rtl rtl/arbiter.sv

  # Use DeepSeek model
  python verify.py --rtl rtl/fsm_controller.sv --provider deepseek --model deepseek-reasoner

  # Run all designs
  python verify.py --all --spec prompts/design_specs.json
        """
    )
    
    parser.add_argument("--rtl", type=str, help="Path to RTL design file (.sv/.v)")
    parser.add_argument("--spec", type=str, default="", help="Path to design specification JSON")
    parser.add_argument("--design", type=str, default="", help="Design key in spec JSON")
    parser.add_argument("--provider", type=str, default="openai",
                        choices=["openai", "deepseek", "local", "gemini"],
                        help="LLM provider")
    parser.add_argument("--model", type=str, default="gpt-4o", help="LLM model name")
    parser.add_argument("--api-key", type=str, default="", help="API key (or use env var)")
    parser.add_argument("--output", type=str, default="output", help="Output directory")
    parser.add_argument("--max-iter", type=int, default=3, help="Max refinement iterations")
    parser.add_argument("--all", action="store_true", help="Run on all designs in rtl/ directory")
    
    args = parser.parse_args()
    
    if args.all:
        # Run on all RTL files
        rtl_dir = Path(__file__).parent.parent / "rtl"
        designs = {
            "fifo.sv": "fifo",
            "arbiter.sv": "arbiter",
            "fsm_controller.sv": "fsm_controller",
            "pipeline.sv": "pipeline"
        }
        
        all_reports = {}
        for rtl_file, design_key in designs.items():
            rtl_path = rtl_dir / rtl_file
            if rtl_path.exists():
                print(f"\n{'='*60}")
                print(f"Processing: {rtl_file}")
                print(f"{'='*60}")
                
                orchestrator = VERIFYOrchestrator(
                    rtl_path=str(rtl_path),
                    spec_path=args.spec or str(Path(__file__).parent.parent / "prompts" / "design_specs.json"),
                    design_key=design_key,
                    llm_provider=args.provider,
                    llm_model=args.model,
                    api_key=args.api_key,
                    output_dir=str(Path(args.output) / design_key),
                    max_refinement_iterations=args.max_iter
                )
                report = orchestrator.run()
                all_reports[design_key] = report
        
        # Save combined report
        combined_path = Path(args.output) / "combined_report.json"
        with open(combined_path, 'w') as f:
            json.dump(all_reports, f, indent=2, default=str)
        print(f"\nCombined report saved to: {combined_path}")
        
    elif args.rtl:
        orchestrator = VERIFYOrchestrator(
            rtl_path=args.rtl,
            spec_path=args.spec,
            design_key=args.design,
            llm_provider=args.provider,
            llm_model=args.model,
            api_key=args.api_key,
            output_dir=args.output,
            max_refinement_iterations=args.max_iter
        )
        orchestrator.run()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
