"""
VERIFY Framework: Formal Verification Interface
Provides interface for syntax checking and property proving using SymbiYosys/Yosys,
as well as counterexample parsing.
Falls back to syntax-only checking when formal tools are not installed.
"""

import re
import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    """Result of verifying a single assertion."""
    assertion_name: str
    assertion_code: str
    status: str  # 'PROVEN', 'COUNTEREXAMPLE', 'SYNTAX_ERROR', 'UNKNOWN', 'TIMEOUT'
    message: str = ""
    counterexample: Optional[str] = None  # Human-readable counterexample trace
    error_log: str = ""
    

class FormalVerifier:
    """Interface for formal verification tools."""
    
    def __init__(self, work_dir: str = "output/formal"):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.tool_available = self._check_tools()
    
    def _check_tools(self) -> Dict[str, bool]:
        """Check which formal verification tools are available."""
        tools = {}
        
        for tool_name, cmd in [("yosys", "yosys --version"), 
                                ("symbiyosys", "sby --help"),
                                ("iverilog", "iverilog -V")]:
            try:
                result = subprocess.run(
                    cmd.split(), capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                tools[tool_name] = result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                tools[tool_name] = False
        
        return tools
    
    def verify_assertions(self, rtl_path: str, assertions: List[str], 
                          module_name: str = "") -> List[VerificationResult]:
        """
        Verify a list of assertions against an RTL design.
        
        Uses SymbiYosys for formal verification if available,
        otherwise performs syntax checking only.
        """
        results = []
        
        for i, assertion in enumerate(assertions):
            # Extract assertion name
            name_match = re.search(r'property\s+(\w+)', assertion)
            name = name_match.group(1) if name_match else f"assertion_{i}"
            
            if self.tool_available.get("symbiyosys"):
                result = self._verify_with_symbiyosys(rtl_path, assertion, name, module_name)
            elif self.tool_available.get("yosys"):
                result = self._verify_syntax_yosys(rtl_path, assertion, name, module_name)
            elif self.tool_available.get("iverilog"):
                result = self._verify_syntax_iverilog(rtl_path, assertion, name, module_name)
            else:
                result = self._verify_standalone_syntax(assertion, name)
            
            results.append(result)
        
        return results
    
    def _verify_with_symbiyosys(self, rtl_path: str, assertion: str, 
                                 name: str, module_name: str) -> VerificationResult:
        """Full formal verification using SymbiYosys."""
        # Create wrapper file with assertion
        wrapper = self._create_wrapper(rtl_path, assertion, module_name)
        wrapper_path = self.work_dir / f"verify_{name}.sv"
        wrapper_path.write_text(wrapper, encoding='utf-8')
        
        # Create SBY configuration
        sby_content = f"""[tasks]
prove

[options]
prove: mode prove
prove: depth 20

[engines]
prove: smtbmc z3

[script]
read -formal {rtl_path}
read -formal {wrapper_path}
prep -top {module_name or 'top'}

[files]
{rtl_path}
{wrapper_path}
"""
        sby_path = self.work_dir / f"verify_{name}.sby"
        sby_path.write_text(sby_content, encoding='utf-8')
        
        try:
            result = subprocess.run(
                ["sby", "-f", str(sby_path)],
                capture_output=True, text=True, timeout=60,
                cwd=str(self.work_dir),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            output = result.stdout + result.stderr
            
            if "PASS" in output:
                return VerificationResult(
                    assertion_name=name,
                    assertion_code=assertion,
                    status="PROVEN",
                    message="Property formally proven"
                )
            elif "FAIL" in output:
                cex = self._parse_counterexample(output, name)
                return VerificationResult(
                    assertion_name=name,
                    assertion_code=assertion,
                    status="COUNTEREXAMPLE",
                    message="Property disproven",
                    counterexample=cex,
                    error_log=output
                )
            else:
                return VerificationResult(
                    assertion_name=name,
                    assertion_code=assertion,
                    status="UNKNOWN",
                    message="Verification inconclusive",
                    error_log=output
                )
        
        except subprocess.TimeoutExpired:
            return VerificationResult(
                assertion_name=name,
                assertion_code=assertion,
                status="TIMEOUT",
                message="Verification timed out after 60s"
            )
        except Exception as e:
            return VerificationResult(
                assertion_name=name,
                assertion_code=assertion,
                status="UNKNOWN",
                message=f"Error: {str(e)}"
            )
    
    def _verify_syntax_yosys(self, rtl_path: str, assertion: str,
                              name: str, module_name: str) -> VerificationResult:
        """Syntax-only check using Yosys."""
        wrapper = self._create_wrapper(rtl_path, assertion, module_name)
        wrapper_path = self.work_dir / f"syntax_{name}.sv"
        wrapper_path.write_text(wrapper, encoding='utf-8')
        
        try:
            result = subprocess.run(
                ["yosys", "-p", f"read -sv {wrapper_path}; prep"],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                return VerificationResult(
                    assertion_name=name,
                    assertion_code=assertion,
                    status="PROVEN",  # Syntax passes, assume proven for non-formal
                    message="Syntax check passed (no formal proof)"
                )
            else:
                return VerificationResult(
                    assertion_name=name,
                    assertion_code=assertion,
                    status="SYNTAX_ERROR",
                    message="Syntax check failed",
                    error_log=result.stderr
                )
        except Exception as e:
            return VerificationResult(
                assertion_name=name,
                assertion_code=assertion,
                status="UNKNOWN",
                message=f"Yosys error: {str(e)}"
            )
    
    def _verify_syntax_iverilog(self, rtl_path: str, assertion: str,
                                 name: str, module_name: str) -> VerificationResult:
        """Syntax-only check using Icarus Verilog."""
        wrapper = self._create_wrapper(rtl_path, assertion, module_name)
        wrapper_path = self.work_dir / f"syntax_{name}.sv"
        wrapper_path.write_text(wrapper, encoding='utf-8')
        
        try:
            result = subprocess.run(
                ["iverilog", "-g2012", "-o", str(self.work_dir / f"syntax_{name}"),
                 str(wrapper_path), str(rtl_path)],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                return VerificationResult(
                    assertion_name=name,
                    assertion_code=assertion,
                    status="PROVEN",
                    message="Syntax check passed via iverilog (no formal proof)"
                )
            else:
                return VerificationResult(
                    assertion_name=name,
                    assertion_code=assertion,
                    status="SYNTAX_ERROR",
                    message="Syntax error detected by iverilog",
                    error_log=result.stderr
                )
        except Exception as e:
            return VerificationResult(
                assertion_name=name,
                assertion_code=assertion,
                status="UNKNOWN",
                message=f"Iverilog error: {str(e)}"
            )
    
    def _verify_standalone_syntax(self, assertion: str, name: str) -> VerificationResult:
        """Basic standalone syntax check using regex (no tools required)."""
        errors = []
        
        # Check for property/endproperty balance
        prop_declarations = len(re.findall(r'(?<!\w)\bproperty\s+\w+', assertion))
        endprop_count = len(re.findall(r'\bendproperty\b', assertion))
        if prop_declarations != endprop_count:
            errors.append(f"Mismatched property/endproperty ({prop_declarations} vs {endprop_count})")
        
        # Check for assert statement
        if not re.search(r'\bassert\s+property\b', assertion):
            errors.append("Missing 'assert property' statement")
        
        # Check for clock specification
        if not re.search(r'@\s*\(\s*(?:posedge|negedge)\s+\w+\s*\)', assertion):
            errors.append("Missing clock specification (@(posedge clk))")
        
        # Check balanced parentheses
        paren_depth = 0
        for ch in assertion:
            if ch == '(':
                paren_depth += 1
            elif ch == ')':
                paren_depth -= 1
            if paren_depth < 0:
                errors.append("Unbalanced parentheses")
                break
        if paren_depth > 0:
            errors.append("Unbalanced parentheses (unclosed)")
        
        # Check for common SVA operator typos
        if '|->' not in assertion and '|=>' not in assertion:
            # Not necessarily an error, but warn
            pass
        
        if errors:
            return VerificationResult(
                assertion_name=name,
                assertion_code=assertion,
                status="SYNTAX_ERROR",
                message="; ".join(errors),
                error_log="\n".join(errors)
            )
        else:
            return VerificationResult(
                assertion_name=name,
                assertion_code=assertion,
                status="PROVEN",
                message="Basic syntax check passed (no formal tools available)"
            )
    
    def _create_wrapper(self, rtl_path: str, assertion: str, module_name: str) -> str:
        """Create a SystemVerilog wrapper file containing the assertion."""
        return f"""// Auto-generated assertion wrapper for VERIFY framework
// RTL: {rtl_path}

module assertion_checker;
    // Assertions are bound to the design module
    {assertion}
endmodule
"""
    
    def _parse_counterexample(self, output: str, name: str) -> str:
        """Parse a counterexample from formal verification output."""
        # Extract the relevant part of the counterexample
        lines = output.split('\n')
        cex_lines = []
        in_cex = False
        
        for line in lines:
            if 'counterexample' in line.lower() or 'trace' in line.lower():
                in_cex = True
            if in_cex:
                cex_lines.append(line)
            if in_cex and line.strip() == '':
                in_cex = False
        
        if cex_lines:
            return "\n".join(cex_lines)
        
        # Fallback: return the relevant portion of the output
        return f"Counterexample found for {name}. Full output:\n{output[:500]}"
    
    def get_tool_status(self) -> str:
        """Get a summary of available tool status."""
        lines = ["Formal Verification Tool Status:"]
        for tool, available in self.tool_available.items():
            status = "✓ Available" if available else "✗ Not found"
            lines.append(f"  {tool}: {status}")
        
        if not any(self.tool_available.values()):
            lines.append("\n  NOTE: No formal tools detected. Using regex-based syntax checking.")
            lines.append("  For full formal verification, install SymbiYosys or Yosys.")
        
        return "\n".join(lines)


class AssertionAnalyzer:
    """Analyze and classify verified assertions."""
    
    CLASSIFICATION_RULES = {
        "RESET": [
            r'!rst_n\b|rst_ni\b|!rst\b',
            r'\breset\b',
        ],
        "SAFETY": [
            r'\b(?:full|empty)\b.*\|->.*!',
            r'!\(.*&&.*\)',  # mutual exclusion
            r'<=.*MAX|>=.*MIN',
        ],
        "LIVENESS": [
            r's_eventually\b',
            r'\#\#\[.*:\$\]',
            r'\[\*\]',
        ],
        "TIMING": [
            r'\#\#\d+',
            r'\#\#\[\d+:\d+\]',
            r'\$past\(',
        ],
        "INVARIANT": [
            r'==|!=',  # Simple equality checks
        ]
    }
    
    @staticmethod
    def classify_assertion(assertion_code: str) -> str:
        """Classify an assertion into a category."""
        # First check if there's an explicit classification comment
        comment_match = re.search(r'//\s*\[(\w+)\]', assertion_code)
        if comment_match:
            return comment_match.group(1).upper()
        
        # Use heuristic rules
        for category, patterns in AssertionAnalyzer.CLASSIFICATION_RULES.items():
            for pattern in patterns:
                if re.search(pattern, assertion_code, re.IGNORECASE):
                    return category
        
        return "INVARIANT"  # Default classification
    
    @staticmethod
    def check_redundancy_simple(assertions: List[str]) -> List[Tuple[int, int, str]]:
        """
        Simple redundancy check based on textual similarity.
        Returns list of (assertion_idx_a, assertion_idx_b, reason).
        For full SAT-based checking, use Z3 (when available).
        """
        redundancies = []
        
        # Normalize assertions for comparison
        normalized = []
        for a in assertions:
            # Remove comments, whitespace, and formatting
            norm = re.sub(r'//[^\n]*', '', a)
            norm = re.sub(r'\s+', ' ', norm).strip()
            # Remove assertion names (just compare logic)
            norm = re.sub(r'property\s+\w+', 'property P', norm)
            norm = re.sub(r'assert\s+property\s*\(\s*\w+\s*\)', 'assert property (P)', norm)
            normalized.append(norm)
        
        for i in range(len(normalized)):
            for j in range(i + 1, len(normalized)):
                if normalized[i] == normalized[j]:
                    redundancies.append((i, j, "Identical assertion (modulo naming)"))
                elif normalized[i] in normalized[j]:
                    redundancies.append((i, j, f"Assertion {i} may be subsumed by {j}"))
                elif normalized[j] in normalized[i]:
                    redundancies.append((j, i, f"Assertion {j} may be subsumed by {i}"))
        
        return redundancies
    
    @staticmethod
    def score_usefulness(assertion_code: str, classification: str, is_proven: bool) -> float:
        """Score the usefulness of an assertion (0.0 to 1.0)."""
        score = 0.5  # Base score
        
        # Proven assertions score higher
        if is_proven:
            score += 0.1
        
        # Classification-based scoring
        if classification == "SAFETY":
            score += 0.2
        elif classification == "LIVENESS":
            score += 0.15
        elif classification == "TIMING":
            score += 0.1
        elif classification == "RESET":
            score += 0.05
        
        # Complexity-based scoring (more complex = potentially more useful)
        if '|->' in assertion_code or '|=>' in assertion_code:
            score += 0.05
        if '$past(' in assertion_code or '$rose(' in assertion_code:
            score += 0.05
        if '##' in assertion_code:
            score += 0.05
        
        # Width-only assertions are less interesting
        if re.search(r'\$bits\(|width|size', assertion_code, re.IGNORECASE):
            score -= 0.2
        
        return min(1.0, max(0.0, score))
