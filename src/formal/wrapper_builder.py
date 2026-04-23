"""
VERIFY V2 — Wrapper Builder
Universal SVA-to-Verilog Transpiler (Robust Logic Version)
"""

import re

class WrapperBuilder:
    def build_bound_wrapper(self, rtl_ctx, assertion_text, top_module=None) -> str:
        module = top_module or rtl_ctx.module_name
        clean_text = self._sanitize_sva(assertion_text)
        
        port_conns = []
        clk_sig = "clk"
        for name, sig in sorted(rtl_ctx.signals.items()):
            if sig.direction in ("input", "output"):
                port_conns.append(f"    .{name}({name})")
            if "clk" in name.lower(): clk_sig = name

        port_str = ",\n".join(port_conns)
        port_decls = self._port_declarations(rtl_ctx)

        return f"""
module assertion_checker (
{port_decls}
);

// Helper for temporal logic
reg f_past_valid = 0;
always @(posedge {clk_sig}) f_past_valid <= 1;

{clean_text}

endmodule

bind {module} assertion_checker u_checker (
{port_str}
);
"""

    def _sanitize_sva(self, text: str) -> str:
        # 1. Aggressive cleaning of LLM/JSON artifacts
        text = text.replace('\\n', ' ').replace('\\t', ' ').replace('\\r', '')
        text = text.replace('\\', '') 
        text = re.sub(r"//.*", "", text)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r'```[a-zA-Z]*', '', text).replace('```', '')
        
        # 2. Normalize operators
        text = re.sub(r'\|->\s*##1', '|=>', text)
        text = re.sub(r'(?<![|<])->', '|->', text)
        text = re.sub(r'(?<![|<])=>', '|=>', text)

        # 3. Extract components
        clk_sig = "clk"
        clk_match = re.search(r'@\s*\(\s*posedge\s+(\w+)\s*\)', text)
        if clk_match: clk_sig = clk_match.group(1)

        disable_cond = None
        dis_match = re.search(r'disable\s+iff\s*\(\s*([^)]+)\s*\)', text)
        if dis_match: disable_cond = dis_match.group(1).strip()

        # Isolate core math
        math = text
        if 'assert property' in text.lower():
            # Find the balanced parenthesis content of the assert property (...)
            start = text.find('(')
            if start != -1:
                depth = 1
                for i in range(start + 1, len(text)):
                    if text[i] == '(': depth += 1
                    elif text[i] == ')': depth -= 1
                    if depth == 0:
                        math = text[start+1:i]
                        break
        
        # Remove clocking/disable metadata from the extracted math string
        math = re.sub(r'@\s*\(\s*posedge\s+\w+\s*\)', '', math, flags=re.IGNORECASE)
        if 'disable iff' in math:
            # Strip disable iff (...)
            math = re.sub(r'disable\s+iff\s*\((?:[^()]*|\([^()]*\))*\)', '', math, flags=re.IGNORECASE)
        
        math = math.replace(';', '').strip()
        while math.startswith('(') and math.endswith(')'):
            math = math[1:-1].strip()

        if not math: return "// Empty expression"

        # 4. RECONSTRUCTION
        res = [f"always @(posedge {clk_sig}) begin"]
        indent = "    "
        if disable_cond:
            res.append(f"{indent}if (!({disable_cond})) begin")
            indent = "        "
        else:
            res.append(f"{indent}begin")

        # Split precisely on temporal operators to avoid OP_LAND (&&) confusion
        if '|=>' in math:
            lhs, rhs = math.split('|=>', 1)
            res.append(f"{indent}if (f_past_valid && $past({lhs.strip()})) assert ({rhs.strip()});")
        elif '|->' in math:
            lhs, rhs = math.split('|->', 1)
            res.append(f"{indent}if ({lhs.strip()}) assert ({rhs.strip()});")
        else:
            res.append(f"{indent}assert ({math.strip()});")

        res.append("    end")
        res.append("end")
        return "\n".join(res)

    def _port_declarations(self, rtl_ctx) -> str:
        lines = []
        for name, sig in sorted(rtl_ctx.signals.items()):
            if sig.direction in ("input", "output"):
                width = f"[{sig.width-1}:0] " if sig.width > 1 else ""
                lines.append(f"    input logic {width}{name}")
        return ",\n".join(lines)