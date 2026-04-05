# VERIFY: Verification-Embedded Refinement with Iterative Feedback Yielding

A powerful, robust framework designed for LLM-assisted SystemVerilog Assertion (SVA) generation with formal verification directly in the loop. 

VERIFY tackles the grueling, manual process of writing formal properties by harnessing Large Language Models, extracting RTL invariants, and systematically validating outputs using mathematical SAT solvers (Yosys/SymbiYosys).

---

## 🏗️ Architecture Duality (V1 vs. V2)

VERIFY natively ships with two execution modes. The project recently underwent a massive architectural migration to support advanced research methodologies.

1. **V1 Pipeline (Default)** 
   A legacy monolithic implementation (`VerifyOrchestrator`) that handles RTL parsing, generation, formal verification, and analysis.
2. **V2 Pipeline (Recommended - use `--v2`)**
   A state-of-the-art, modular 8-stage pipeline. V2 decouples every phase of the assertion lifecycle into distinct Python packages natively supporting complex Generation Strategies and Pre-Formal Quality Gating.

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your API Key
# The framework natively supports multiple LLMs. OpenAI is the default.
set OPENAI_API_KEY=your_key_here     # Windows (OpenAI)
export OPENAI_API_KEY=your_key_here  # Linux/Mac (OpenAI)

# Alternatively, set Gemini or DeepSeek keys:
# export GEMINI_API_KEY=your_key_here
# export DEEPSEEK_API_KEY=your_key_here

# 3. Run the Advanced V2 Pipeline on a specific design
# It defaults to OpenAI. You can override it using `--provider`
python src/verify.py --rtl rtl/fifo.sv --spec prompts/design_specs.json --design fifo --v2 --provider openai
# python src/verify.py ... --v2 --provider gemini
# python src/verify.py ... --v2 --provider deepseek

# 4. Run the Legacy V1 Pipeline
python src/verify.py --rtl rtl/fifo.sv --spec prompts/design_specs.json --design fifo

# 5. Run without an API Key (Mock Mode)
# If no key is found, the framework intelligently uses Mock Regex Responses to test the pipeline structure.
python src/verify.py --rtl rtl/fifo.sv --spec prompts/design_specs.json --design fifo --v2
```

---

## 📂 Deep Dive: Project Structure & Code Navigation

To truly understand how VERIFY works over the `--v2` pipeline, here is a detailed breakdown of what is happening inside every single file in the repository.

### `VERIFY/src/` — The Core Engine
The V2 codebase is divided into 8 decoupled architectural packages to enforce clean data boundaries.

#### 0. Entry Point
- **`verify.py`**: The main CLI script. It parses arguments (like `--rtl` and `--v2`). If `--v2` is flagged, it imports the V2 orchestrator and begins the pipeline. If not, it falls back to the V1 monolith.
- **`llm_interface.py`**: A generic abstraction class capable of communicating with `Gemini` or `OpenAI` via APIs, handling retries, API keys, and saving local mock-responses if APIs are unavailable.
- **`formal_verifier.py`**: The legacy hardware interface logic that wraps OS subprocess calls to `iverilog`, `yosys`, and `sby`.

#### 1. Data Models (`src/core/`)
- **`models.py`**: The beating heart of the V2 type system. It defines all strict `dataclass` representations used heavily across the stages. Key structures include `RTLContext` (holds parsed SV signals), `SpecContext` (holds natural language requirements), `CandidateAssertion` (holds the LLM-generated property and its provenance hash), and `PipelineArtifact` (the final schema for the JSON report).
- **`orchestrator_v2.py`**: Contains `VerifyOrchestratorV2`. This acts as the conductor, instantiating and dependency-injecting the 8 stages, mapping the output of ingestion into generation, running gates, formal solvers, and loops.

#### 2. Ingest Stage A: Context Building (`src/ingest/`)
- **`rtl_context.py`**: Contains `RTLContextBuilder`. It wraps the legacy SV parser, using regex to extract module names, input/output signals, parameters, and auto-infers clock (`clk`) and reset (`rst_n`) behavior.
- **`spec_context.py`**: Contains `SpecContextBuilder`. Converts raw English specs from JSON into atomic `SpecClause` objects, intelligently assigning them classes (e.g., `Safety`, `Liveness`) through NLP keyword evaluation.
- **`trace_context.py`**: Contains `TraceContextBuilder`. Wraps the V1 `InvariantMiner`. It extracts pseudo-random testbench simulations and runs mathematical thresholds to uncover probable behavioral invariants to feed to the LLMs.

#### 3. Stage B: Assertion Generation (`src/generate/`)
- **`prompt_engine.py`**: Contains `PromptEngine`. A rendering pipeline for SVA instructions. It crucially enforces provenance tracking by applying deterministic hashes (SHA-256) to prompt strings, ensuring every generated candidate tracks perfectly via a `source_prompt_id`.
- **`candidate_generator.py`**: Contains `CandidateGenerator`. The multi-threaded LLM orchestrator. It manages the 5 different prompting techniques (`_gen_spec_driven`, `_gen_rtl_driven`, etc.), issues specific calls to the `PromptEngine`, talks to the LLM, and parses out raw SV strings into structured `CandidateAssertion` lists.

#### 4. Stage C: Pre-Formal Quality Gate (`src/gate/`)
- **`pre_formal_gate.py`**: Contains `PreFormalGate`. Since SAT solvers are extraordinarily expensive, this filters bad assertions instantly using four heuristic checks: C1 (Confirms no non-existent signals were hallucinated), C2 (Checks for syntactically balanced `property`/`endproperty` formatting), and C3 (Screens for vacuous tautologies where `1 |-> 1`).
- **`canonicalizer.py`**: Normalizes assertion text (strips spaces and comments) and hashes them to create canonical signatures. If Strategy 1 and Strategy 4 generate the mathematically identical SV line, the canonicalizer perfectly deduplicates them so we verify it only once.

#### 5. Stage D: Formal Validation (`src/formal/`)
- **`formal_runner.py`**: Contains `FormalRunner`. Bridges our Python data objects into standard hardware formal toolchains, converting text execution outputs from Yosys/Iverilog into strict `AssertionStatus` Enums (like `PROVEN_FORMAL`, `DISPROVEN`, or `SYNTAX_ERROR`).
- **`wrapper_builder.py`**: Auto-generates standard SystemVerilog `bind` wrappers, allowing us to legally attach our LLM-generated properties to the original Design Under Test (DUT) dynamically.
- **`cex_parser.py`**: Extracts the Counter-Example (CEX) traces dumped when Yosys/SBY fails a bounded model check, minimizing the dump down to human-readable step-by-step failures meant to be digested by the LLM in refinement.

#### 6. Stage E: Refinement (`src/refine/`)
- **`refinement_loop.py`**: Contains `RefinementLoop`. When the `FormalRunner` traps a syntax error or a valid counter-example trace, this module injects the CEX/Err feedback explicitly to the LLM interface and asks it to re-write the assertion inline, looping up to a specified iteration limit.

#### 7. Stage F: Analysis (`src/analyze/`)
- **`classifier.py`**: Tagged-analysis mapping asserting mathematical intents systematically back to structural origins.
- **`redundancy_graph.py`**: Maps subsumption edges. If Assertion A is broad, and Assertion B is highly specific, it generates logic graphs highlighting where assertions overlap to save overall verification execution time.
- **`scoring.py`**: Ranks the assertions on usefulness and novelty scores based on their operational history passing the Formal runner.
- **`coverage_matrix.py`**: Employs mapping to connect verified/proven assertions directly to the initial lines of the `SpecContext`, exposing visually the percentage of initial specifications tested successfully.

#### 8. Stage G: Reporting (`src/report/`)
- **`artifact_writer.py`**: The cleanup crew. Serializes the massive runtime telemetry array holding all generations, hash ids, run outputs, paths, CEX logs, and context into clean JSON `sync_fifo_report.json`. Emits the verified SV bindings strictly to a `.sv` file.
- **`metrics.py`**: Provides rapid statistical aggregation parsing the entire run calculating the average cycle runtime, gated rejection percentage, and successful validation numbers.

### Supporting Folders
- **`VERIFY/rtl/`**: Contains raw SystemVerilog DUTs (e.g., `fifo.sv`, `pipeline.sv`).
- **`VERIFY/prompts/`**: 
  - `design_specs.json`: The human-written constraints tied structurally to the RTL files.
  - `templates.py`: The exact prompt templating language injected dynamically by the Prompt Engine during generation.
- **`VERIFY/output_v2/`**: 
  - `assertions/`: Pluggable `.sv` files containing final approved outputs.
  - `reports/`: Massive telemetry dumps outlining all prompt inputs, toolchain results, refinement strings, and failure causes perfectly linked by canonical hashing.

---

## 🧠 The 5 Generation Strategies (V2)

Instead of generically asking an LLM to "write assertions," the `candidate_generator.py` intelligently attacks the verification problem from 5 different angles natively:

1. **Specification-Driven**: Feeds explicit english logic (e.g., "Full flag goes high if..."). Excellent for high-level functional intent mapping directly to specification text.
2. **RTL-Driven**: Passes the AST representations internally to the LLM omitting specifications, capturing implicit mechanical behaviors inside FSMs and loops standard documents rarely note.
3. **Invariant-Seeded**: Feeds simulated trace mathematics mathematically to ground cycle latencies and relationships.
4. **ChIRAAG-Style Semantic Breakdown**: Granular targeted micro-generations focused strictly step by step resolving standard large "Lost-in-Context" pipeline bottlenecks.
5. **Holistic Generation**: Cross-correlates all three modalities (Specs + Code + Invariants) in a giant payload to catch highly complex multidimensional edge-cases dynamically requiring deep linkage.

---

## 🛠️ Required Dependencies

While the framework runs syntactical verification fallback modes in Python natively to prevent API breakage when running mock generations, achieving **true mathematical formal proofing** requires physical installation of standard automated hardware testbench suites:

- `iverilog` (Icarus Verilog for baseline syntax checking)
- `yosys` (Open-source synthesis suite)
- `sby` (SymbiYosys front-end for formal verification)

**Python Packages:**
```bash
pip install google-genai openai
```
