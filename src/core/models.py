"""
VERIFY V2: Core Data Models
============================
All dataclasses and enums used throughout the V2 pipeline.
These serve as the common schema layer across all stages.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ── Enums ──────────────────────────────────────────────────────────────

class AssertionStatus(str, Enum):
    """Status of an assertion after validation."""
    PARSE_REJECTED = "PARSE_REJECTED"
    SIGNAL_INVALID = "SIGNAL_INVALID"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    SYNTAX_OK_ONLY = "SYNTAX_OK_ONLY"
    PROVEN_FORMAL = "PROVEN_FORMAL"
    DISPROVEN_CEX = "DISPROVEN_CEX"
    TIMEOUT = "TIMEOUT"
    TOOL_ERROR = "TOOL_ERROR"
    UNKNOWN = "UNKNOWN"


class IntentType(str, Enum):
    """Classification of assertion intent."""
    RESET = "RESET"
    SAFETY = "SAFETY"
    LIVENESS = "LIVENESS"
    TIMING = "TIMING"
    INVARIANT = "INVARIANT"


# ── Stage A: Context Models ───────────────────────────────────────────

@dataclass
class ModuleSignal:
    """A single signal extracted from the RTL module."""
    name: str
    direction: str          # input / output / internal
    width: int
    dtype: str = "logic"


@dataclass
class RTLContext:
    """Normalized context extracted from the RTL source."""
    module_name: str
    rtl_path: str
    raw_code: str
    signals: Dict[str, ModuleSignal] = field(default_factory=dict)
    parameters: Dict[str, str] = field(default_factory=dict)
    fsm_states: List[str] = field(default_factory=list)
    clock_candidates: List[str] = field(default_factory=list)
    reset_candidates: List[str] = field(default_factory=list)
    dependency_groups: List[List[str]] = field(default_factory=list)


@dataclass
class SpecClause:
    """A single requirement clause from the specification."""
    clause_id: str
    intent: IntentType
    text: str
    mapped_signals: List[str] = field(default_factory=list)
    ambiguity_score: float = 0.0


@dataclass
class SpecContext:
    """Normalized context extracted from the specification document."""
    design_key: str
    design_name: str
    description: str
    clauses: List[SpecClause] = field(default_factory=list)
    signal_descriptions: Dict[str, str] = field(default_factory=dict)


@dataclass
class TraceContext:
    """Normalized context extracted from simulation traces."""
    source: str             # "vcd" | "synthetic"
    cycles: int
    signals_present: List[str] = field(default_factory=list)
    mined_invariants: List[str] = field(default_factory=list)
    invariant_confidence: Dict[str, float] = field(default_factory=dict)


# ── Stage B: Candidate Assertions ─────────────────────────────────────

@dataclass
class CandidateAssertion:
    """A single candidate assertion produced by any generation strategy."""
    candidate_id: str
    assertion_text: str
    property_name: str
    intent_hint: Optional[IntentType] = None
    source_strategy: str = ""
    source_prompt_id: str = ""
    used_signals: List[str] = field(default_factory=list)
    spec_clause_refs: List[str] = field(default_factory=list)
    canonical_hash: Optional[str] = None
    quality_flags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Stage C: Gate ─────────────────────────────────────────────────────

@dataclass
class GateResult:
    """Result of the pre-formal quality gate for one candidate."""
    candidate_id: str
    accepted: bool
    reject_reason: Optional[str] = None
    normalized_text: Optional[str] = None
    canonical_hash: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    # Set when fuzzy signal correction was applied; downstream should use this
    # text instead of the original candidate assertion_text.
    corrected_text: Optional[str] = None
    fuzzy_corrections: Dict[str, str] = field(default_factory=dict)  # original → corrected


# ── Stage D: Formal Validation ────────────────────────────────────────

@dataclass
class ValidationResult:
    """Result of formal / syntax validation for one candidate."""
    candidate_id: str
    status: AssertionStatus
    tool: str
    message: str
    proof_depth: Optional[int] = None
    counterexample: Optional[str] = None
    error_log: str = ""
    runtime_sec: float = 0.0


# ── Stage E: Refinement ──────────────────────────────────────────────

@dataclass
class RefinementAction:
    """Record of a single refinement attempt on a failed candidate."""
    candidate_id: str
    iteration: int
    verdict: str            # ASSERTION_WRONG / DESIGN_BUG / SPEC_AMBIGUOUS / UNFIXABLE
    revised_assertion_text: Optional[str] = None
    rationale: str = ""
    consumed_cex: bool = False


# ── Stage F: Analysis ────────────────────────────────────────────────

@dataclass
class AssertionAnalysis:
    """Analysis record for one accepted assertion."""
    candidate_id: str
    final_intent: IntentType = IntentType.INVARIANT
    usefulness_score: float = 0.0
    novelty_score: float = 0.0
    redundant_with: List[str] = field(default_factory=list)
    subsumes: List[str] = field(default_factory=list)
    coverage_clauses: List[str] = field(default_factory=list)


# ── Stage G: Pipeline-wide ───────────────────────────────────────────

@dataclass
class PipelineMetrics:
    """Aggregate metrics for the entire pipeline run."""
    total_candidates: int = 0
    gated_in: int = 0
    syntax_ok: int = 0
    proven_formal: int = 0
    disproven: int = 0
    refined: int = 0
    final_kept: int = 0
    llm_calls: int = 0
    total_runtime_sec: float = 0.0


@dataclass
class PipelineArtifact:
    """The unified report produced at the end of a V2 pipeline run."""
    run_id: str
    rtl_context: RTLContext = field(default_factory=lambda: RTLContext("", "", ""))
    spec_context: SpecContext = field(default_factory=lambda: SpecContext("", "", ""))
    trace_context: TraceContext = field(default_factory=lambda: TraceContext("synthetic", 0))
    candidates: List[CandidateAssertion] = field(default_factory=list)
    gate_results: List[GateResult] = field(default_factory=list)
    validation_results: List[ValidationResult] = field(default_factory=list)
    refinement_actions: List[RefinementAction] = field(default_factory=list)
    analyses: List[AssertionAnalysis] = field(default_factory=list)
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)
