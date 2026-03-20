# VERIFY: Verification-Embedded Refinement with Iterative Feedback Yielding

A novel framework for LLM-assisted SystemVerilog Assertion (SVA) generation with formal-in-the-loop validation.

## Key Innovations

1. **Counterexample-Driven Refinement** — Formal BMC counterexamples fed back to LLM
2. **Multi-Strategy Generation** — Spec-driven + RTL-driven + invariant-seeded approaches
3. **Dynamic Invariant Mining** — Daikon-inspired trace analysis
4. **SAT-Based Redundancy Detection** — Formal implication checking
5. **Signal-Group Generation** — Captures cross-signal temporal properties

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
set OPENAI_API_KEY=your_key_here   # Windows
# export OPENAI_API_KEY=your_key   # Linux/Mac

# Run on a single design
python src/verify.py --rtl rtl/fifo.sv --spec prompts/design_specs.json --design fifo

# Run on all designs
python src/verify.py --all --spec prompts/design_specs.json

# Run without API key (mock mode - tests infrastructure)
python src/verify.py --rtl rtl/fifo.sv --spec prompts/design_specs.json --design fifo
```

## Project Structure

```
VERIFY/
├── rtl/                           # Target RTL designs
│   ├── fifo.sv                    # Synchronous FIFO
│   ├── arbiter.sv                 # Round-robin arbiter
│   ├── fsm_controller.sv         # Traffic light FSM
│   └── pipeline.sv               # 3-stage pipelined datapath
├── src/                           # Framework source code
│   ├── verify.py                  # Main orchestrator (4-stage pipeline)
│   ├── rtl_parser.py              # RTL structural analysis
│   ├── llm_interface.py           # LLM API interface with logging
│   ├── invariant_miner.py         # Dynamic invariant mining
│   └── formal_verifier.py         # Formal verification interface
├── prompts/                       # Prompt engineering
│   ├── templates.py               # 7 prompt templates
│   └── design_specs.json          # Design specifications
├── output/                        # Generated outputs
│   ├── assertions/                # Generated SVA files
│   ├── logs/                      # Prompt/response logs
│   └── reports/                   # JSON analysis reports
├── requirements.txt
└── README.md
```

## Pipeline Stages

### Stage 1: Specification Decomposition & Invariant Mining
- Parse RTL structure (signals, FSMs, dependencies)
- Load and format design specifications
- Mine candidate invariants from simulation traces

### Stage 2: Multi-Strategy Assertion Generation
- **Spec-Driven**: Generate from NL specifications
- **RTL-Driven**: Generate from RTL code analysis
- **Invariant-Seeded**: Validate and formalize mined invariants

### Stage 3: Formal-in-the-Loop Validation & Refinement
- Syntax checking (SymbiYosys/Yosys/iverilog or regex fallback)
- Property proving via BMC
- Counterexample-driven LLM refinement loop

### Stage 4: Analysis & Redundancy Elimination
- Classification: SAFETY / LIVENESS / INVARIANT / RESET / TIMING
- Redundancy detection (textual + SAT-based)
- Usefulness scoring
