# Prompt templates for the VERIFY framework

SPEC_DRIVEN_GENERATION = """You are an expert hardware verification engineer.

## Design: {design_name}
## Relevant RTL Code:
```systemverilog
{rtl_code}
Design Specification:
{spec_text}

Signal Definitions:
{signal_defs}

Task:
Generate SystemVerilog Assertions (SVA) for this design.

Requirements:
Use INLINE assertions ONLY (assert property (...)).

Do NOT use property ... endproperty blocks.

Do NOT use labels (e.g., write assert property, NOT p_name: assert property).

CRITICAL ANTI-HALLUCINATION: Use the exact signal names provided in the RTL Code. NEVER use placeholder names like 'rtl_signal' or 'expression'.

CRITICAL SYNTAX: Every assertion MUST explicitly define the clock edge inside the parenthesis: @(posedge clk).

Output Format:
Return ONLY the SVA code block:


// [SAFETY] Description using actual signal names
assert property ( @(posedge clk) disable iff (!rst_n) real_signal_a |-> real_signal_b );
"""

RTL_DRIVEN_GENERATION = """You are an expert hardware verification engineer.

RTL Code:

{rtl_code}
Requirements:
Use INLINE assertions ONLY (assert property (...)).

Do NOT use labels or property/endproperty blocks.

CRITICAL: Only use exact signals present in the RTL. No placeholders.

CRITICAL: Every assertion MUST explicitly define the clock edge: @(posedge clk).

Output Format:

// [INVARIANT] Description
assert property ( @(posedge clk) disable iff (!rst_n) condition |-> result );
"""

INVARIANT_SEEDED_GENERATION = """You are an expert hardware verification engineer.

RTL Code:

{rtl_code}
Mined Candidate Invariants:
{mined_invariants}

Requirements:
Translate MEANINGFUL invariants into INLINE assert property (...) statements.

Do NOT use labels or property/endproperty blocks.

CRITICAL: Use exact RTL signal names. No placeholder text.

CRITICAL: Every assertion MUST explicitly define the clock edge: @(posedge clk).

Output Format:

// [LIVENESS] Description
assert property ( @(posedge clk) disable iff (!rst_n) invariant_expr );
"""

COUNTEREXAMPLE_ANALYSIS = """Analyze the counterexample.

RTL Code (excerpt):

{rtl_excerpt}
If ASSERTION_WRONG, provide the refined assertion using a single INLINE assert property (...) statement.
You MUST include @(posedge clk) inside the assertion. Do NOT use labels.
"""

SYNTAX_CORRECTION = """Fix the syntax errors in the following assertions.
Use INLINE assert property (...) statements. You MUST include @(posedge clk). Do NOT use labels. Do NOT hallucinate signal names. Return ONLY the corrected assertions.
"""

ASSERTION_CLASSIFICATION = """Classify the following SVAs:
{assertions}
"""

REDUNDANCY_ANALYSIS = """Analyze redundancies in these SVAs:
{assertions}
"""

HOLISTIC_GENERATION = """Generate robust SVAs combining Spec, RTL, and invariants.
Use INLINE assert property (...) statements. Do NOT use labels.
CRITICAL: You MUST use actual design signals. NEVER use placeholders like 'rtl_signal'.
CRITICAL: Every assertion MUST explicitly define the clock edge: @(posedge clk).

Output Format:

// [TIMING] Description
assert property ( @(posedge clk) disable iff (!rst_n) event_a |=> event_b );
"""

SANGAM_MAPPING = """Map natural language specification terms to exact RTL signal names.
{signal_defs}
Return JSON dictionary.
"""

CHIRAAG_SEMANTIC_BREAKDOWN = """Extract hardware behavior into a semantic table JSON.
{signal_map_json}
Return JSON array.
"""

CHIRAAG_CONTEXT_GENERATION = """Translate semantic breakdown into SVA.
Use INLINE assert property (...) statements. Do NOT use labels.
CRITICAL: Use exact RTL signal names. You MUST include @(posedge clk).
Return ONLY SVA code block.
"""