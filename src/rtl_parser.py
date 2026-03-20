"""
VERIFY Framework: RTL Parser Module
Extracts signal information, module hierarchy, and builds dependency graphs from Verilog/SystemVerilog files.
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional


@dataclass
class Signal:
    """Represents an RTL signal."""
    name: str
    direction: str  # 'input', 'output', 'wire', 'reg', 'logic'
    width: int = 1
    is_array: bool = False
    description: str = ""


@dataclass
class FSMState:
    """Represents an FSM state."""
    name: str
    encoding: str
    transitions: List[Tuple[str, str]] = field(default_factory=list)  # [(condition, next_state)]


@dataclass 
class ModuleInfo:
    """Parsed RTL module information."""
    name: str
    signals: Dict[str, Signal] = field(default_factory=dict)
    parameters: Dict[str, str] = field(default_factory=dict)
    fsm_states: List[FSMState] = field(default_factory=list)
    always_blocks: List[str] = field(default_factory=list)
    assign_statements: List[str] = field(default_factory=list)
    raw_code: str = ""
    signal_groups: List[List[str]] = field(default_factory=list)


class RTLParser:
    """Parse Verilog/SystemVerilog files to extract structural information."""
    
    def __init__(self):
        self.modules: Dict[str, ModuleInfo] = {}
    
    def parse_file(self, filepath: str) -> ModuleInfo:
        """Parse an RTL file and extract module information."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"RTL file not found: {filepath}")
        
        code = path.read_text(encoding='utf-8')
        module_info = ModuleInfo(name=path.stem, raw_code=code)
        
        # Extract module name
        module_match = re.search(r'module\s+(\w+)', code)
        if module_match:
            module_info.name = module_match.group(1)
        
        # Extract parameters
        module_info.parameters = self._extract_parameters(code)
        
        # Extract signals (inputs, outputs, wires, regs, logic)
        module_info.signals = self._extract_signals(code)
        
        # Extract FSM states (typedef enum)
        module_info.fsm_states = self._extract_fsm_states(code)
        
        # Extract always blocks
        module_info.always_blocks = self._extract_always_blocks(code)
        
        # Extract assign statements
        module_info.assign_statements = self._extract_assigns(code)
        
        # Build signal groups based on dependency analysis
        module_info.signal_groups = self._build_signal_groups(module_info)
        
        self.modules[module_info.name] = module_info
        return module_info
    
    def _extract_parameters(self, code: str) -> Dict[str, str]:
        """Extract parameter declarations."""
        params = {}
        # Match: parameter TYPE NAME = VALUE
        for match in re.finditer(r'parameter\s+(?:\w+\s+)?(\w+)\s*=\s*([^,\)]+)', code):
            params[match.group(1).strip()] = match.group(2).strip()
        return params
    
    def _extract_signals(self, code: str) -> Dict[str, Signal]:
        """Extract all signal declarations."""
        signals = {}
        
        # Patterns for different signal types
        patterns = [
            # input/output logic [width] name
            (r'(input|output)\s+logic\s*(\[([^\]]+)\])?\s*(\w+)', 'io'),
            # plain logic declarations
            (r'(?<!input\s)(?<!output\s)logic\s*(\[([^\]]+)\])?\s*(\w+)', 'logic'),
        ]
        
        # Extract input/output signals
        for match in re.finditer(
            r'(input|output)\s+logic\s*(?:\[([^\]]+)\])?\s*([\w,\s]+?)(?=[,\);])', 
            code
        ):
            direction = match.group(1)
            width_str = match.group(2)
            names = match.group(3).strip()
            
            width = self._parse_width(width_str) if width_str else 1
            
            for name in re.split(r'[,\s]+', names):
                name = name.strip()
                if name and name not in ('', 'begin', 'end'):
                    signals[name] = Signal(
                        name=name,
                        direction=direction,
                        width=width
                    )
        
        # Extract internal logic/reg/wire declarations
        for match in re.finditer(
            r'(?:logic|reg|wire)\s*(?:\[([^\]]+)\])?\s*(\w+)\s*(?:\[([^\]]+)\])?\s*;',
            code
        ):
            width_str = match.group(1)
            name = match.group(2)
            
            if name not in signals and name not in ('begin', 'end', 'if', 'else', 'case'):
                width = self._parse_width(width_str) if width_str else 1
                signals[name] = Signal(
                    name=name,
                    direction='internal',
                    width=width
                )
        
        return signals
    
    def _parse_width(self, width_str: str) -> int:
        """Parse width from bit range string like '7:0' or 'DATA_WIDTH-1:0'."""
        if not width_str:
            return 1
        try:
            parts = width_str.split(':')
            if len(parts) == 2:
                # Try to evaluate simple expressions
                high = parts[0].strip()
                low = parts[1].strip()
                if high.isdigit() and low.isdigit():
                    return int(high) - int(low) + 1
            return -1  # Parameterized width
        except:
            return -1
    
    def _extract_fsm_states(self, code: str) -> List[FSMState]:
        """Extract FSM state definitions from typedef enum."""
        states = []
        
        # Match typedef enum logic [...] { STATE1 = val, ... } type_name;
        enum_match = re.search(
            r'typedef\s+enum\s+logic\s*\[[^\]]+\]\s*\{([^}]+)\}\s*(\w+)',
            code
        )
        
        if enum_match:
            enum_body = enum_match.group(1)
            # Parse each state
            for state_match in re.finditer(r'(\w+)\s*=\s*([^,}]+)', enum_body):
                states.append(FSMState(
                    name=state_match.group(1).strip(),
                    encoding=state_match.group(2).strip()
                ))
            
            # Try to extract transitions from case statements
            case_blocks = re.findall(r'case\s*\([^)]+\)(.*?)endcase', code, re.DOTALL)
            for case_block in case_blocks:
                for state in states:
                    # Find transitions from this state
                    state_section = re.search(
                        rf'{state.name}\s*:\s*begin(.*?)end',
                        case_block, re.DOTALL
                    )
                    if state_section:
                        # Find next_state assignments
                        for trans in re.finditer(
                            r'(?:next_state|next)\s*(?:=|<=)\s*(\w+)',
                            state_section.group(1)
                        ):
                            next_st = trans.group(1)
                            state.transitions.append(("", next_st))
        
        return states
    
    def _extract_always_blocks(self, code: str) -> List[str]:
        """Extract always_ff and always_comb blocks."""
        blocks = []
        # Simple extraction - find always blocks
        for match in re.finditer(
            r'(always_ff\s+@\([^)]+\)\s+begin.*?end|always_comb\s+begin.*?end)',
            code, re.DOTALL
        ):
            blocks.append(match.group(0))
        return blocks
    
    def _extract_assigns(self, code: str) -> List[str]:
        """Extract continuous assign statements."""
        assigns = []
        for match in re.finditer(r'assign\s+(.+?);', code):
            assigns.append(match.group(1).strip())
        return assigns
    
    def _build_signal_groups(self, module: ModuleInfo) -> List[List[str]]:
        """Build signal groups based on dependency analysis."""
        # Build dependency graph: signal -> set of signals it depends on
        deps: Dict[str, Set[str]] = {s: set() for s in module.signals}
        
        all_signal_names = set(module.signals.keys())
        
        # Analyze always blocks and assigns for dependencies
        code_blocks = module.always_blocks + [f"assign {a}" for a in module.assign_statements]
        
        for block in code_blocks:
            # Find all LHS assignments
            lhs_signals = set()
            for match in re.finditer(r'(\w+)\s*(?:<=|=)', block):
                name = match.group(1)
                if name in all_signal_names:
                    lhs_signals.add(name)
            
            # Find all RHS signal references
            rhs_signals = set()
            for name in all_signal_names:
                if re.search(rf'\b{re.escape(name)}\b', block):
                    rhs_signals.add(name)
            
            # LHS depends on RHS
            for lhs in lhs_signals:
                for rhs in rhs_signals - lhs_signals:
                    deps.setdefault(lhs, set()).add(rhs)
        
        # Group signals that share dependencies (connected components)
        visited = set()
        groups = []
        
        # Build undirected adjacency
        adj: Dict[str, Set[str]] = {s: set() for s in all_signal_names}
        for s, dep_set in deps.items():
            for d in dep_set:
                if d in adj:
                    adj[s].add(d)
                    adj[d].add(s)
        
        for signal in all_signal_names:
            if signal not in visited:
                # BFS to find connected component
                group = []
                queue = [signal]
                while queue:
                    current = queue.pop(0)
                    if current in visited:
                        continue
                    visited.add(current)
                    group.append(current)
                    for neighbor in adj.get(current, set()):
                        if neighbor not in visited:
                            queue.append(neighbor)
                if group:
                    groups.append(sorted(group))
        
        return groups
    
    def get_signal_names(self, module_name: str = None) -> List[str]:
        """Get list of all signal names for a module."""
        if module_name and module_name in self.modules:
            return list(self.modules[module_name].signals.keys())
        elif self.modules:
            last_module = list(self.modules.values())[-1]
            return list(last_module.signals.keys())
        return []
    
    def get_io_signals(self, module_name: str = None) -> Dict[str, Signal]:
        """Get only input/output signals."""
        module = self.modules.get(module_name) or list(self.modules.values())[-1]
        return {
            name: sig for name, sig in module.signals.items()
            if sig.direction in ('input', 'output')
        }
    
    def to_summary(self, module_name: str = None) -> str:
        """Generate a human-readable summary of the parsed module."""
        module = self.modules.get(module_name) or list(self.modules.values())[-1]
        
        lines = [f"Module: {module.name}", ""]
        
        if module.parameters:
            lines.append("Parameters:")
            for name, val in module.parameters.items():
                lines.append(f"  {name} = {val}")
            lines.append("")
        
        lines.append("Signals:")
        for name, sig in sorted(module.signals.items()):
            width_str = f"[{sig.width}-bit]" if sig.width > 1 else ""
            lines.append(f"  {sig.direction:8s} {width_str:10s} {name}")
        lines.append("")
        
        if module.fsm_states:
            lines.append("FSM States:")
            for state in module.fsm_states:
                trans_str = ", ".join([f"-> {t[1]}" for t in state.transitions])
                lines.append(f"  {state.name} = {state.encoding} {trans_str}")
            lines.append("")
        
        if module.signal_groups:
            lines.append("Signal Groups (by dependency):")
            for i, group in enumerate(module.signal_groups):
                lines.append(f"  Group {i+1}: {', '.join(group)}")
        
        return "\n".join(lines)


def parse_design(rtl_path: str) -> ModuleInfo:
    """Convenience function to parse a single RTL file."""
    parser = RTLParser()
    return parser.parse_file(rtl_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        info = parse_design(sys.argv[1])
        parser = RTLParser()
        parser.modules[info.name] = info
        print(parser.to_summary(info.name))
    else:
        print("Usage: python rtl_parser.py <rtl_file.sv>")
