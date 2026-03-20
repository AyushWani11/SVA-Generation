"""
VERIFY Framework: Dynamic Invariant Miner
Mines candidate invariants from simulation traces using Daikon-inspired techniques.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class TracePoint:
    """A single simulation trace point."""
    time: int
    signals: Dict[str, int]


@dataclass
class CandidateInvariant:
    """A candidate invariant mined from simulation traces."""
    expression: str
    category: str  # 'equality', 'range', 'implication', 'temporal', 'constant'
    confidence: float  # 0.0 to 1.0
    support: int  # number of trace points supporting this
    signals_involved: List[str] = field(default_factory=list)
    
    def to_sva(self) -> str:
        """Convert to SVA-like expression (not full assertion, just condition)."""
        return self.expression


class InvariantMiner:
    """Mine candidate invariants from VCD or simulation trace files."""
    
    def __init__(self, signal_names: List[str] = None):
        self.traces: List[TracePoint] = []
        self.signal_names = signal_names or []
        self.invariants: List[CandidateInvariant] = []
    
    def load_vcd(self, vcd_path: str):
        """Load a VCD (Value Change Dump) file."""
        # Simple VCD parser
        path = Path(vcd_path)
        if not path.exists():
            raise FileNotFoundError(f"VCD file not found: {vcd_path}")
        
        signal_map = {}  # VCD id -> signal name
        current_time = 0
        current_values = {}
        
        with open(path, 'r') as f:
            in_definitions = True
            for line in f:
                line = line.strip()
                
                if line == '$end' and in_definitions:
                    continue
                
                if line.startswith('$var'):
                    # $var wire 1 ! signal_name $end
                    parts = line.split()
                    if len(parts) >= 5:
                        vcd_id = parts[3]
                        sig_name = parts[4]
                        signal_map[vcd_id] = sig_name
                        current_values[sig_name] = 0
                
                elif line.startswith('$enddefinitions'):
                    in_definitions = False
                
                elif line.startswith('#'):
                    # Time stamp
                    new_time = int(line[1:])
                    if current_values and new_time > current_time:
                        self.traces.append(TracePoint(
                            time=current_time,
                            signals=dict(current_values)
                        ))
                    current_time = new_time
                
                elif not in_definitions and len(line) > 0:
                    # Value change: either single bit (0/1 + id) or multi-bit (b... id)
                    if line[0] in ('0', '1', 'x', 'z'):
                        val = 1 if line[0] == '1' else 0
                        vcd_id = line[1:]
                        if vcd_id in signal_map:
                            current_values[signal_map[vcd_id]] = val
                    elif line.startswith('b'):
                        parts = line.split()
                        if len(parts) == 2:
                            try:
                                val = int(parts[0][1:], 2)
                            except ValueError:
                                val = 0
                            vcd_id = parts[1]
                            if vcd_id in signal_map:
                                current_values[signal_map[vcd_id]] = val
        
        # Add final trace point
        if current_values:
            self.traces.append(TracePoint(time=current_time, signals=dict(current_values)))
        
        if not self.signal_names:
            self.signal_names = list(signal_map.values())
    
    def load_traces_from_dict(self, traces: List[Dict[str, int]]):
        """Load traces from a list of dictionaries (for testing without VCD)."""
        for i, t in enumerate(traces):
            self.traces.append(TracePoint(time=i * 10, signals=t))
        if not self.signal_names and traces:
            self.signal_names = list(traces[0].keys())
    
    def mine_all(self) -> List[CandidateInvariant]:
        """Run all mining algorithms and return candidate invariants."""
        self.invariants = []
        
        if not self.traces:
            return self.invariants
        
        self.invariants.extend(self._mine_constant_signals())
        self.invariants.extend(self._mine_range_invariants())
        self.invariants.extend(self._mine_equality_invariants())
        self.invariants.extend(self._mine_implication_invariants())
        self.invariants.extend(self._mine_mutual_exclusion())
        self.invariants.extend(self._mine_temporal_patterns())
        
        return self.invariants
    
    def _mine_constant_signals(self) -> List[CandidateInvariant]:
        """Find signals that never change value."""
        invariants = []
        for sig in self.signal_names:
            values = set()
            for tp in self.traces:
                if sig in tp.signals:
                    values.add(tp.signals[sig])
            
            if len(values) == 1:
                val = list(values)[0]
                invariants.append(CandidateInvariant(
                    expression=f"{sig} == {val}",
                    category="constant",
                    confidence=1.0,
                    support=len(self.traces),
                    signals_involved=[sig]
                ))
        
        return invariants
    
    def _mine_range_invariants(self) -> List[CandidateInvariant]:
        """Find min/max range for each signal."""
        invariants = []
        for sig in self.signal_names:
            values = []
            for tp in self.traces:
                if sig in tp.signals:
                    values.append(tp.signals[sig])
            
            if values:
                min_val = min(values)
                max_val = max(values)
                
                if max_val > 0:  # Only interesting for non-trivial ranges
                    invariants.append(CandidateInvariant(
                        expression=f"({sig} >= {min_val}) && ({sig} <= {max_val})",
                        category="range",
                        confidence=0.8,  # Less confident - may not have seen all values
                        support=len(values),
                        signals_involved=[sig]
                    ))
        
        return invariants
    
    def _mine_equality_invariants(self) -> List[CandidateInvariant]:
        """Find pairs of signals that are always equal or are complements."""
        invariants = []
        signals = [s for s in self.signal_names if any(s in tp.signals for tp in self.traces)]
        
        for i, sig_a in enumerate(signals):
            for sig_b in signals[i+1:]:
                equal_count = 0
                complement_count = 0
                total = 0
                
                for tp in self.traces:
                    if sig_a in tp.signals and sig_b in tp.signals:
                        total += 1
                        if tp.signals[sig_a] == tp.signals[sig_b]:
                            equal_count += 1
                        if tp.signals[sig_a] == (1 - tp.signals[sig_b]):
                            complement_count += 1
                
                if total > 0:
                    if equal_count == total:
                        invariants.append(CandidateInvariant(
                            expression=f"{sig_a} == {sig_b}",
                            category="equality",
                            confidence=0.9,
                            support=total,
                            signals_involved=[sig_a, sig_b]
                        ))
                    elif complement_count == total and total > 5:
                        invariants.append(CandidateInvariant(
                            expression=f"{sig_a} == !{sig_b}",
                            category="equality",
                            confidence=0.9,
                            support=total,
                            signals_involved=[sig_a, sig_b]
                        ))
        
        return invariants
    
    def _mine_implication_invariants(self) -> List[CandidateInvariant]:
        """Find signal implications: if A then B."""
        invariants = []
        # Only check 1-bit signals for implications
        bool_signals = []
        for sig in self.signal_names:
            values = set()
            for tp in self.traces:
                if sig in tp.signals:
                    values.add(tp.signals[sig])
            if values <= {0, 1}:
                bool_signals.append(sig)
        
        for sig_a in bool_signals:
            for sig_b in bool_signals:
                if sig_a == sig_b:
                    continue
                
                # Check: sig_a=1 => sig_b=? 
                a_true_b_true = 0
                a_true_b_false = 0
                
                for tp in self.traces:
                    if sig_a in tp.signals and sig_b in tp.signals:
                        if tp.signals[sig_a] == 1:
                            if tp.signals[sig_b] == 1:
                                a_true_b_true += 1
                            else:
                                a_true_b_false += 1
                
                total_a_true = a_true_b_true + a_true_b_false
                if total_a_true > 3:  # Need enough samples
                    if a_true_b_false == 0:
                        invariants.append(CandidateInvariant(
                            expression=f"{sig_a} |-> {sig_b}",
                            category="implication",
                            confidence=0.85,
                            support=total_a_true,
                            signals_involved=[sig_a, sig_b]
                        ))
                    if a_true_b_true == 0:
                        invariants.append(CandidateInvariant(
                            expression=f"{sig_a} |-> !{sig_b}",
                            category="implication",
                            confidence=0.85,
                            support=total_a_true,
                            signals_involved=[sig_a, sig_b]
                        ))
        
        return invariants
    
    def _mine_mutual_exclusion(self) -> List[CandidateInvariant]:
        """Find signals that are never simultaneously true."""
        invariants = []
        bool_signals = []
        for sig in self.signal_names:
            values = set()
            for tp in self.traces:
                if sig in tp.signals:
                    values.add(tp.signals[sig])
            if values <= {0, 1}:
                bool_signals.append(sig)
        
        for i, sig_a in enumerate(bool_signals):
            for sig_b in bool_signals[i+1:]:
                both_true = False
                for tp in self.traces:
                    if (sig_a in tp.signals and sig_b in tp.signals and
                        tp.signals[sig_a] == 1 and tp.signals[sig_b] == 1):
                        both_true = True
                        break
                
                if not both_true:
                    # Check that both signals were actually true at some point
                    a_ever_true = any(tp.signals.get(sig_a, 0) == 1 for tp in self.traces)
                    b_ever_true = any(tp.signals.get(sig_b, 0) == 1 for tp in self.traces)
                    
                    if a_ever_true and b_ever_true:
                        invariants.append(CandidateInvariant(
                            expression=f"!({sig_a} && {sig_b})",
                            category="implication",
                            confidence=0.9,
                            support=len(self.traces),
                            signals_involved=[sig_a, sig_b]
                        ))
        
        return invariants
    
    def _mine_temporal_patterns(self) -> List[CandidateInvariant]:
        """Find temporal patterns: signal A rising implies signal B changes within N cycles."""
        invariants = []
        bool_signals = []
        for sig in self.signal_names:
            values = set()
            for tp in self.traces:
                if sig in tp.signals:
                    values.add(tp.signals[sig])
            if values <= {0, 1}:
                bool_signals.append(sig)
        
        for sig_a in bool_signals:
            for sig_b in bool_signals:
                if sig_a == sig_b:
                    continue
                
                # Find rising edges of sig_a and check if sig_b rises within N cycles
                for max_delay in [1, 2, 3]:
                    pattern_holds = True
                    pattern_tested = False
                    
                    for i in range(1, len(self.traces)):
                        prev = self.traces[i-1].signals.get(sig_a, 0)
                        curr = self.traces[i].signals.get(sig_a, 0)
                        
                        if prev == 0 and curr == 1:  # Rising edge of sig_a
                            pattern_tested = True
                            # Check if sig_b becomes 1 within max_delay steps
                            found = False
                            for j in range(i, min(i + max_delay + 1, len(self.traces))):
                                if self.traces[j].signals.get(sig_b, 0) == 1:
                                    found = True
                                    break
                            if not found:
                                pattern_holds = False
                                break
                    
                    if pattern_holds and pattern_tested:
                        invariants.append(CandidateInvariant(
                            expression=f"$rose({sig_a}) |-> ##[0:{max_delay}] {sig_b}",
                            category="temporal",
                            confidence=0.7,
                            support=len(self.traces),
                            signals_involved=[sig_a, sig_b]
                        ))
                        break  # Found pattern with smallest delay
        
        return invariants
    
    def to_text(self) -> str:
        """Format all mined invariants as text for LLM consumption."""
        if not self.invariants:
            return "No invariants mined (no simulation traces available)."
        
        lines = [f"=== Mined Candidate Invariants ({len(self.invariants)} total) ===\n"]
        
        categories = {}
        for inv in self.invariants:
            categories.setdefault(inv.category, []).append(inv)
        
        for cat, invs in sorted(categories.items()):
            lines.append(f"\n[{cat.upper()}] ({len(invs)} invariants)")
            for inv in invs:
                conf_str = f"{inv.confidence*100:.0f}%"
                lines.append(f"  - {inv.expression}  (confidence: {conf_str}, support: {inv.support})")
        
        return "\n".join(lines)
    
    def generate_synthetic_traces(self, design_name: str, rtl_code: str, num_cycles: int = 100) -> List[Dict[str, int]]:
        """
        Generate synthetic simulation traces based on RTL code analysis.
        This is a simplified simulation for when no VCD file is available.
        """
        import random
        traces = []
        
        if design_name == "sync_fifo" or "fifo" in design_name.lower():
            traces = self._sim_fifo(num_cycles)
        elif design_name == "round_robin_arbiter" or "arbiter" in design_name.lower():
            traces = self._sim_arbiter(num_cycles)
        elif design_name == "fsm_controller" or "fsm" in design_name.lower():
            traces = self._sim_fsm(num_cycles)
        elif design_name == "pipeline_datapath" or "pipeline" in design_name.lower():
            traces = self._sim_pipeline(num_cycles)
        else:
            # Generic random traces
            for _ in range(num_cycles):
                traces.append({sig: random.randint(0, 1) for sig in self.signal_names})
        
        return traces
    
    def _sim_fifo(self, n: int) -> List[Dict[str, int]]:
        """Simulate FIFO behavior."""
        import random
        traces = []
        wr_ptr, rd_ptr, count = 0, 0, 0
        depth = 16
        
        for _ in range(n):
            wr_en = random.randint(0, 1)
            rd_en = random.randint(0, 1)
            full = 1 if count == depth else 0
            empty = 1 if count == 0 else 0
            
            actual_wr = wr_en and not full
            actual_rd = rd_en and not empty
            
            traces.append({
                "wr_en": wr_en, "rd_en": rd_en,
                "full": full, "empty": empty,
                "count": count, "wr_ptr": wr_ptr, "rd_ptr": rd_ptr
            })
            
            if actual_wr and not actual_rd:
                count += 1
                wr_ptr = (wr_ptr + 1) % depth
            elif actual_rd and not actual_wr:
                count -= 1
                rd_ptr = (rd_ptr + 1) % depth
            elif actual_wr and actual_rd:
                wr_ptr = (wr_ptr + 1) % depth
                rd_ptr = (rd_ptr + 1) % depth
        
        return traces
    
    def _sim_arbiter(self, n: int) -> List[Dict[str, int]]:
        """Simulate round-robin arbiter behavior."""
        import random
        traces = []
        last_grant = 0
        
        for _ in range(n):
            req = random.randint(0, 15)  # 4-bit request
            
            # Round-robin: scan from last_grant+1
            grant = 0
            if req:
                for offset in range(4):
                    idx = (last_grant + 1 + offset) % 4
                    if req & (1 << idx):
                        grant = 1 << idx
                        last_grant = idx
                        break
            
            active = 1 if grant else 0
            
            traces.append({
                "req": req, "grant": grant, "active": active
            })
        
        return traces
    
    def _sim_fsm(self, n: int) -> List[Dict[str, int]]:
        """Simulate FSM controller behavior."""
        import random
        traces = []
        state = 0  # IDLE=0, GREEN=1, YELLOW=2, RED=3
        
        for _ in range(n):
            start = random.randint(0, 1)
            sensor = random.randint(0, 1)
            timer_expired = random.randint(0, 1)
            
            light_green = 1 if state == 1 else 0
            light_yellow = 1 if state == 2 else 0
            light_red = 1 if state == 3 else 0
            
            traces.append({
                "state": state, "start": start, "sensor": sensor,
                "timer_expired": timer_expired,
                "light_green": light_green, "light_yellow": light_yellow,
                "light_red": light_red
            })
            
            # State transitions
            if state == 0 and start:
                state = 1
            elif state == 1 and (timer_expired or not sensor):
                state = 2
            elif state == 2 and timer_expired:
                state = 3
            elif state == 3 and timer_expired:
                state = 0
        
        return traces
    
    def _sim_pipeline(self, n: int) -> List[Dict[str, int]]:
        """Simulate pipeline datapath behavior."""
        import random
        traces = []
        s1_valid, s2_valid, s3_valid = 0, 0, 0
        s2_result, s3_result = 0, 0
        
        for _ in range(n):
            valid_in = random.randint(0, 1)
            stall = random.choice([0, 0, 0, 1])  # 25% stall
            flush = random.choice([0, 0, 0, 0, 0, 0, 0, 1])  # 12.5% flush
            opcode = random.randint(0, 3)
            operand_a = random.randint(0, 255)
            operand_b = random.randint(0, 255)
            
            traces.append({
                "valid_in": valid_in, "stall": stall, "flush": flush,
                "opcode": opcode, "result_valid": s3_valid,
                "s1_valid": s1_valid, "s2_valid": s2_valid, "s3_valid": s3_valid
            })
            
            if flush:
                s1_valid = s2_valid = s3_valid = 0
            elif not stall:
                s3_valid = s2_valid
                s2_valid = s1_valid
                s1_valid = valid_in
        
        return traces
