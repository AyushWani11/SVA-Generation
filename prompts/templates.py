# Prompt templates for the VERIFY framework
# Each template is a function that returns a formatted prompt string

SPEC_DRIVEN_GENERATION = """You are an expert hardware verification engineer specializing in SystemVerilog Assertions (SVA).

## Design: {design_name}
## Description: {description}

## Relevant RTL Code:
```systemverilog
{rtl_code}
```

## Design Specification:
{spec_text}

## Signal Definitions:
{signal_defs}

## Task:
Generate SystemVerilog Assertions (SVA) for this design. Cover the following categories:

1. **RESET properties**: Verify correct behavior during and after reset
2. **SAFETY properties**: "Something bad never happens" (e.g., mutual exclusion, overflow prevention)
3. **LIVENESS properties**: "Something good eventually happens" (e.g., requests eventually granted)
4. **FUNCTIONAL INVARIANTS**: Properties that must always hold during normal operation
5. **TIMING properties**: Clock-cycle-accurate temporal relationships

## Requirements:
- Each assertion MUST use the `property`/`endproperty` and `assert property` syntax
- Use `disable iff (!rst_n)` for properties that should not be checked during reset
- Use correct SystemVerilog temporal operators: `|->`, `|=>`, `##N`, `[*N]`, `$past()`, `$rose()`, `$fell()`, `$stable()`
- Do NOT invent signal names - only use signals from the RTL code above
- Classify each assertion with a comment: // [SAFETY], // [LIVENESS], // [INVARIANT], // [RESET], or // [TIMING]

## Output Format:
Return ONLY the SVA code block, with each assertion having:
1. A descriptive comment with classification tag
2. A named property
3. An assert statement

```systemverilog
// [CLASSIFICATION] Description of what this assertion checks
property p_name;
    @(posedge clk) disable iff (!rst_n)
    antecedent |-> consequent;
endproperty
assert property (p_name) else $error("p_name failed");
```
"""

RTL_DRIVEN_GENERATION = """You are an expert hardware verification engineer. Analyze the following RTL code and generate SystemVerilog Assertions that verify the implementation matches typical design intent.

## RTL Code:
```systemverilog
{rtl_code}
```

## Task:
Generate SVA assertions by analyzing the RTL code structure. Focus on:
1. **State machine transitions**: Valid state encodings, legal transitions
2. **Counter boundaries**: Overflow/underflow protection, wrap-around behavior
3. **Handshake protocols**: Request-grant, valid-ready pairs
4. **Data integrity**: Data preservation across pipeline stages, FIFO ordering
5. **Control flow**: Enable/disable conditions, priority encoding correctness

## Requirements:
- Each assertion MUST be syntactically correct SystemVerilog
- Use `property`/`endproperty` syntax with `assert property`
- Use `disable iff (!rst_n)` where appropriate
- Classify each: // [SAFETY], // [LIVENESS], // [INVARIANT], // [RESET], or // [TIMING]
- Only use signal names present in the RTL code

Return ONLY the SVA code block.
"""

INVARIANT_SEEDED_GENERATION = """You are an expert hardware verification engineer. I have mined the following candidate invariants from simulation traces of a hardware design.

## Design: {design_name}
## Description: {description}

## RTL Code:
```systemverilog
{rtl_code}
```

## Mined Candidate Invariants:
{mined_invariants}

## Task:
Analyze each mined invariant and:
1. **Determine if it is meaningful**: Is this a real design invariant or a coincidental pattern?
2. **Determine if it is trivially true**: Is this obvious from the code structure?
3. **Formalize as SVA**: Convert meaningful, non-trivial invariants into SystemVerilog Assertions
4. **Propose additional invariants**: Suggest invariants the simulation might have missed

## Requirements:
- Mark each invariant as: MEANINGFUL, TRIVIAL, or SPURIOUS
- For MEANINGFUL invariants, generate proper SVA with property/endproperty syntax
- Classify each: // [SAFETY], // [LIVENESS], // [INVARIANT]
- Do NOT invent signal names

## Output Format:
For each mined invariant, output:
```
INVARIANT: <original invariant text>
VERDICT: MEANINGFUL / TRIVIAL / SPURIOUS
REASON: <brief explanation>
SVA (if MEANINGFUL):
```systemverilog
// [CLASSIFICATION] Description
property p_name;
    @(posedge clk) disable iff (!rst_n)
    expression;
endproperty
assert property (p_name);
```
```

Then list any ADDITIONAL invariants you propose.
"""

COUNTEREXAMPLE_ANALYSIS = """You are an expert hardware verification engineer. A SystemVerilog Assertion has been formally disproven by a bounded model checker, which produced a counterexample trace.

## Design: {design_name}

## The Failing Assertion:
```systemverilog
{assertion_code}
```

## Counterexample Trace:
{counterexample_trace}

## Design Specification (relevant excerpt):
{spec_excerpt}

## RTL Code (relevant excerpt):
```systemverilog
{rtl_excerpt}
```

## Task:
Analyze the counterexample and determine the root cause.
First, explain your debugging reasoning step-by-step in a `<step_by_step_reasoning>` block.
Then determine if the issue is:

1. **ASSERTION_WRONG**: The assertion incorrectly captures the design intent. The design behavior shown in the counterexample is correct per the specification.
   - If so, provide a REFINED assertion that correctly captures the intended property.

2. **DESIGN_BUG**: The assertion is correct per the specification, but the RTL implementation has a bug that the counterexample reveals.
   - If so, describe the bug and what the correct behavior should be.

3. **SPEC_AMBIGUOUS**: The specification is ambiguous about this behavior.
   - If so, describe the ambiguity and suggest how to resolve it.

## Output Format:
<step_by_step_reasoning>
1. Analyzing counterexample trace...
2. Checking against Specification...
3. Checking against RTL...
4. Concluding root cause...
</step_by_step_reasoning>

```
VERDICT: ASSERTION_WRONG / DESIGN_BUG / SPEC_AMBIGUOUS
ANALYSIS: <detailed explanation of what the counterexample shows>
```

If ASSERTION_WRONG, also provide:
```systemverilog
// [CLASSIFICATION] Refined: <description>
property p_refined_name;
    @(posedge clk) disable iff (!rst_n)
    <corrected_expression>;
endproperty
assert property (p_refined_name) else $error("p_refined_name failed");
```
"""

SYNTAX_CORRECTION = """You are an expert SystemVerilog engineer. Fix the syntax errors in the following assertions.

## Assertions with errors:
```systemverilog
{assertion_code}
```

## Syntax Error Messages:
{error_messages}

## Available Signal Names (from RTL):
{signal_names}

## Rules:
- Fix ONLY syntax issues, do NOT change the assertion's semantic intent
- Do NOT invented new signal names
- Use proper SystemVerilog assertion syntax
- Return the corrected assertions ONLY

```systemverilog
<corrected assertions here>
```
"""

ASSERTION_CLASSIFICATION = """Classify each of the following SystemVerilog Assertions into exactly one category.

## Assertions:
{assertions}

## Categories:
- **SAFETY**: "Something bad never happens" - bounds checks, mutual exclusion, overflow prevention, valid state encoding
- **LIVENESS**: "Something good eventually happens" - eventual response, eventual grant, data eventually delivered
- **INVARIANT**: A property that must hold at every cycle - reset correctness, combinational relationships, constant conditions
- **RESET**: Specifically about reset behavior - initial state after reset
- **TIMING**: Specific clock-cycle timing relationships - pipeline latency, handshake timing

## Output:
For each assertion, output one line:
ASSERTION: <assertion_name> -> CATEGORY: <category>
"""

REDUNDANCY_ANALYSIS = """You are a formal verification expert. Analyze the following set of proven SystemVerilog Assertions for redundancy.

## Proven Assertions:
{assertions}

## Task:
Identify pairs where one assertion logically implies another (making the implied one redundant).

For each redundancy found, explain:
1. Which assertion is redundant
2. Which assertion subsumes it
3. Brief logical justification

## Output:
```
REDUNDANCY: <assertion_A> IMPLIES <assertion_B>
REASON: <brief explanation>
KEEP: <assertion_A>
REMOVE: <assertion_B>
```

If no redundancies found, output: NO_REDUNDANCIES_FOUND
"""

HOLISTIC_GENERATION = """You are an expert hardware verification engineer. I am providing you with the comprehensive context for a hardware design, including its specification, RTL implementation, and dynamically mined simulation invariants.

## Design: {design_name}
## Description: {description}

## Design Specification:
{spec_text}

## RTL Code:
```systemverilog
{rtl_code}
```

## Signal Definitions:
{signal_defs}

## Dynamically Mined Invariants (from simulation traces):
{mined_invariants}

## Task:
Generate a robust set of SystemVerilog Assertions (SVA) that comprehensively verify this design. Synthesize insights from the specification, RTL structure, and mined invariants simultaneously.

## Requirements:
- Analyze the design step-by-step first. Write your reasoning in a `<step_by_step_reasoning>` block.
- Identify complex cross-signal relationships and corner cases.
- Convert meaningful invariants and specification rules into correct SVA.
- Each assertion MUST use proper `property`/`endproperty` and `assert property` syntax.
- Classify each: // [SAFETY], // [LIVENESS], // [INVARIANT], // [RESET], or // [TIMING]

## Output Format:
<step_by_step_reasoning>
1. Reviewing Specification...
2. Analyzing RTL structure...
3. Evaluating Mined Invariants...
4. Planning SystemVerilog Assertions...
</step_by_step_reasoning>

```systemverilog
// [CLASSIFICATION] Description
property p_name;
    @(posedge clk) disable iff (!rst_n)
    expression |-> consequence;
endproperty
assert property (p_name) else $error("p_name failed");
```
"""

SANGAM_MAPPING = """You are an expert hardware verification engineer. Your task is to map natural language specification terms to exact RTL signal names.

## Design Name: {design_name}
## Description: {description}

## Relevant RTL Code:
```systemverilog
{rtl_code}
```

## Available RTL Signals:
{signal_defs}

## Design Specification:
{spec_text}

## Task:
Map the key terms, behavioral states, and signals mentioned in the Design Specification to the exact Available RTL Signals. 
Do not invent signal names. If a spec term does not clearly map to a signal, explain why.

## Output Format:
Return a JSON dictionary mapping the natural language terms to the exact RTL signals.
```json
{{
  "Acknowledgment Signal": "ack_o",
  "Transmit Enable": "tx_en_i"
}}
```
"""

CHIRAAG_SEMANTIC_BREAKDOWN = """You are an expert hardware verification engineer. Your task is to extract hardware behavior from a specification and break it down into a standardized semantic table.

## Design Specification:
{spec_text}

## Signal Mapping (SANGAM):
{signal_map_json}

## Task:
Analyze the functionality, timing, and safety rules in the specification. Break each distinct property down into a JSON list of objects containing:
1. "trigger": The condition that starts the check (using exact RTL signals from the mapping).
2. "action": The expected hardware behavior or consequence.
3. "latency": The clock cycle offset (e.g., "##1", "##[1:3]", "same cycle").
4. "description": A short English explanation.

## Output Format:
Return ONLY a JSON array of objects.
```json
[
  {{
    "trigger": "req_i && !busy_o",
    "action": "ack_o == 1",
    "latency": "##1",
    "description": "A request while not busy must be acknowledged in the next cycle."
  }}
]
```
"""

CHIRAAG_CONTEXT_GENERATION = """You are an expert hardware verification engineer specializing in lightweight SystemVerilog Assertions (SVA) generation.

## Design: {design_name}
## RTL Code:
```systemverilog
{rtl_code}
```

## Semantic Breakdown (ChIRAAG extracted rules):
{semantic_breakdown_json}

## Task:
Translate the provided semantic breakdown into syntactically correct SystemVerilog Assertions.
Follow this rigid few-shot template strictly. 

## Requirements:
- Use `property`/`endproperty` and `assert property` syntax.
- Use `disable iff (!rst_n)` for properties that should not be checked during reset.
- Inject the precise Trigger, Latency, and Action from the Semantic Breakdown.
- Do NOT hallucinate signals; refer to the provided exact variables.
- Classify each: // [SAFETY], // [LIVENESS], // [INVARIANT], // [RESET], or // [TIMING].

## Few-Shot Template Example:
```systemverilog
// [TIMING] A request while not busy must be acknowledged in the next cycle.
property p_req_ack;
    @(posedge clk) disable iff (!rst_n) 
    (req_i && !busy_o) |-> ##1 (ack_o == 1);
endproperty
assert property (p_req_ack) else $error("p_req_ack failed");
```

## Output:
Return ONLY the SVA code block covering all rules in the Semantic Breakdown.
"""
