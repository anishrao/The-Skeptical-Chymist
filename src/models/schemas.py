"""Pydantic schemas for Condition-Mechanism-Outcome (CMO) graphs, synthesis recipes, literature gaps, and experiment predictions."""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class SynthesisParameter(BaseModel):
    name: str = Field(
        description="Standardized name of the synthesis parameter or reagent (e.g., 'AgNO3 concentration', 'HCl concentration', 'CTAB concentration', 'Temperature', 'Seed volume', 'Ascorbic acid ratio', 'pH')"
    )
    raw_value: str = Field(
        description="Reported value or range with units as written in the paper (e.g., '0.10 mM', '25-60 °C', 'pH 2.1')"
    )
    role: Literal[
        "gold_precursor",
        "silver_additive",
        "halide_additive",
        "surfactant",
        "reducing_agent",
        "pH_modifier",
        "seed_parameter",
        "temperature",
        "time",
        "solvent_or_other",
    ] = Field(description="Functional role in nanomaterial synthesis")


class MorphologyOutcome(BaseModel):
    morphology: str = Field(
        description="Resulting nanoparticle shape (e.g., 'gold nanobipyramids', 'pentatwinned rods', 'spherical byproducts')"
    )
    length_nm: Optional[str] = Field(
        default=None, description="Longitudinal tip-to-tip length in nm (if reported)"
    )
    width_nm: Optional[str] = Field(
        default=None, description="Equatorial width/diameter in nm (if reported)"
    )
    aspect_ratio: Optional[str] = Field(
        default=None, description="Aspect ratio (length/width) if reported"
    )
    volume_nm3: Optional[str] = Field(
        default=None, description="Single-particle volume in nm^3 or relative volume change"
    )
    lspr_peak_nm: Optional[str] = Field(
        default=None, description="Longitudinal localized surface plasmon resonance (LSPR) peak wavelength in nm"
    )
    shape_yield_percent: Optional[str] = Field(
        default=None, description="Bipyramid shape purity / yield percentage before or after purification"
    )


class SynthesisRecipeRun(BaseModel):
    run_id: str = Field(description="Short identifier for the experimental run or table row")
    parameters: List[SynthesisParameter] = Field(
        default_factory=list, description="Synthesis conditions used in this run"
    )
    outcome: MorphologyOutcome = Field(description="Resulting morphological and optical outcome")
    source_section: str = Field(
        description="Where this run was found (e.g., 'Main Text Table 1', 'SI Figure S4')"
    )


class CMOPerturbationEdge(BaseModel):
    """Condition-Mechanism-Outcome (CMO) directional causal relationship extracted from a paper."""

    perturbed_parameter: str = Field(
        description="The synthesis variable X that was changed (e.g., 'AgNO3 concentration', 'HCl addition', 'Reaction temperature', 'Seed concentration')"
    )
    perturbation_direction: Literal["increase", "decrease", "addition_or_substitution", "non_monotonic_sweep"] = Field(
        description="How the parameter X was varied"
    )
    parameter_range_tested: str = Field(
        description="Specific quantitative range over which X was varied (e.g., '0.02 mM to 0.15 mM AgNO3')"
    )
    fixed_boundary_conditions: List[str] = Field(
        default_factory=list,
        description="Crucial fixed conditions C under which this perturbation holds (e.g., 'CTAB = 100 mM', 'pentatwinned citrate seeds', 'T = 30 °C')"
    )
    proposed_mechanism: str = Field(
        description="Physical chemistry / mechanistic intermediate M explaining WHY ΔX causes ΔY (e.g., 'Underpotential deposition of Ag0 on {110} stepped facets slows equatorial growth relative to {111} tips')"
    )
    affected_observable: str = Field(
        description="The output property Y (e.g., 'Bipyramid volume', 'Aspect ratio', 'Longitudinal LSPR peak', 'Tip sharpness', 'Shape yield')"
    )
    outcome_direction: Literal[
        "increase",
        "decrease",
        "no_significant_change",
        "non_monotonic_optimum",
        "phase_or_shape_transition",
    ] = Field(description="Direction of change in observable Y when X is perturbed")
    quantitative_effect: str = Field(
        description="Quantitative summary of the change in Y (e.g., 'Volume decreases from 45,000 nm^3 to 18,000 nm^3; LSPR blue-shifts from 850 nm to 720 nm')"
    )
    evidence_quote: str = Field(
        description="Short verbatim or near-verbatim quote from the paper/SI supporting this causal link"
    )
    from_supplementary_info: bool = Field(
        default=False, description="True if extracted from Supplementary Information (SI)"
    )


class PaperExtraction(BaseModel):
    paper_id: str = Field(description="Short filename or unique ID of the paper")
    title: str = Field(description="Full title of the paper")
    authors_short: str = Field(description="First author et al.")
    publication_year: Optional[int] = Field(
        default=None, description="4-digit publication year (crucial for temporal holdout filtering)"
    )
    doi: Optional[str] = Field(default=None, description="DOI string if present in the PDF")
    core_system_studied: str = Field(
        description="Primary material system (e.g., 'Seed-mediated gold nanobipyramid synthesis in CTAB/AgNO3')"
    )
    parameters_varied: List[str] = Field(
        description="List of standardized synthesis parameters systematically varied in this paper (MUST include at least 1 parameter)"
    )
    parameters_held_constant: List[str] = Field(
        description="List of synthesis parameters kept constant across experiments in this paper"
    )
    synthesis_runs: List[SynthesisRecipeRun] = Field(
        description="Explicit experimental recipes and outcomes"
    )
    cmo_edges: List[CMOPerturbationEdge] = Field(
        description="All directional Condition-Mechanism-Outcome (ΔX -> Mechanism -> ΔY) relationships reported in this paper (MUST extract at least 2-5 causal edges)"
    )
    untested_assumptions_or_limitations: List[str] = Field(
        description="Assumptions made by the authors or boundary regimes they noted but did not test"
    )
    key_cited_references: List[str] = Field(
        description="Titles or DOIs of the 3-5 most important foundational mechanistic papers cited in the text"
    )


class LiteratureGap(BaseModel):
    gap_id: str = Field(description="Identifier like GAP-1, GAP-2")
    gap_category: Literal[
        "PARAMETER_SPACE_HOLE",
        "MECHANISTIC_CONTRADICTION",
        "COUPLED_VARIABLE_CONFOUNDING",
        "UNEXPLORED_KINETIC_THERMODYNAMIC_REGIME",
    ] = Field(description="Concrete taxonomy of the gap (avoids generic 'future work' platitudes)")
    title: str = Field(description="Concise scientific title of the gap")
    parameter_coordinates: List[str] = Field(
        description="Exact synthesis variables involved (e.g., ['AgNO3/HAuCl4 ratio', 'Reaction Temperature', 'Cl-/Br- co-halide ratio'])"
    )
    evidence_from_corpus: str = Field(
        description="Specific citation-backed explanation showing what Paper A did vs. Paper B, and what exact intersection or contradiction remains unresolved"
    )
    competing_mechanistic_hypotheses: List[str] = Field(
        description="At least 2 competing physical chemistry predictions for what could happen in this unexplored gap"
    )
    proposed_decisive_experiment: str = Field(
        description="A concrete, falsifiable wet-lab experiment (with specific parameter sweeps and readouts like UV-Vis LSPR, TEM volume/aspect ratio) that resolves this gap"
    )
    specificity_score: int = Field(
        ge=1, le=10, description="Self-rated specificity (1=generic wishlist, 10=exact parameter & mechanism coordinates)"
    )


class LiteratureGapReport(BaseModel):
    domain_summary: str
    explored_parameter_space_summary: str
    gaps: List[LiteratureGap]
    cross_questioning_refinements: Optional[List[str]] = Field(
        default=None,
        description="How the Cross-Questioning Critic filtered out trivial gaps or sharpened the mechanistic contradictions"
    )


class CrossQuestioningChallenge(BaseModel):
    round_number: int
    failure_mode_targeted: Literal[
        "CONFOUNDING_SYNTHESIS_VARIABLE",
        "NON_MONOTONIC_REGIME_BOUNDARY",
        "MASS_AND_STOICHIOMETRY_CONSERVATION",
        "CONTRADICTORY_LITERATURE_EVIDENCE",
        "KINETIC_VS_THERMODYNAMIC_DOMINANCE",
    ]
    sharp_question: str = Field(
        description="Adversarial physical-chemistry question challenging the Proposer's initial prediction or gap claim"
    )
    physical_rationale_for_doubt: str = Field(
        description="Why a simple linear extrapolation could fail here (e.g., mass balance, secondary nucleation, micelle destabilization, redox potential shift)"
    )
    external_search_query_needed: Optional[str] = Field(
        default=None,
        description="If external literature verification is required to answer this challenge, specify a targeted search query for OpenAlex/EuropePMC"
    )


class CrossQuestioningCycle(BaseModel):
    challenges: List[CrossQuestioningChallenge]


class ObservablePredictionItem(BaseModel):
    observable: str = Field(
        description="Target property (e.g., 'Bipyramid single-particle volume', 'Aspect ratio', 'Longitudinal LSPR peak wavelength', 'Tip truncation / sharpness', 'Shape purity / yield')"
    )
    predicted_direction: Literal[
        "increase",
        "decrease",
        "no_significant_change",
        "non_monotonic_increase_then_decrease",
        "non_monotonic_decrease_then_increase",
    ]
    predicted_magnitude_or_range: str = Field(
        description="Expected quantitative or semi-quantitative shift (e.g., 'Volume decreases by ~30-50%', 'LSPR blue-shifts by 40-80 nm')"
    )
    mechanistic_justification: str = Field(
        description="Step-by-step physical chemistry explanation linking ΔX to this observable"
    )


class ExperimentPredictionResult(BaseModel):
    experiment_prompt: str
    perturbed_variable: str
    perturbation_summary: str
    primary_prediction_summary: str = Field(
        description="Clear, direct answer to what happens when condition X is changed"
    )
    observable_predictions: List[ObservablePredictionItem]
    causal_mechanism_chain: List[str] = Field(
        description="Ordered step-by-step causal chain: [ΔX] -> [Solution Speciation / Redox / Surfactant effect] -> [Facet Growth Rate / Nucleation Kinetics] -> [Final Morphology & Volume]"
    )
    conservation_and_regime_check: str = Field(
        description="Explicit check of mass balance (Au0 conversion vs. seed count vs. particle volume) and whether any regime boundary (e.g., secondary nucleation) is crossed"
    )
    supporting_paper_citations: List[str]
    confidence_zero_to_one: float = Field(ge=0.0, le=1.0)
    key_uncertainties_or_boundary_conditions: List[str]


class BlindedHeldOutBenchmarkCase(BaseModel):
    """Extracted from a held-out paper in data/held_out_papers/ to test if the agent can predict its results."""

    held_out_paper_id: str
    title: str
    publication_year: Optional[int] = None
    doi: Optional[str] = None
    blinded_baseline_protocol: str = Field(
        description="The starting synthesis recipe and fixed conditions from the Experimental section, with NO results or outcomes mentioned"
    )
    perturbation_question: str = Field(
        description="The experimental question to ask the agent: 'Starting from the baseline protocol, what happens to the gold bipyramid morphology (specifically particle volume, length, width, aspect ratio, LSPR peak, and yield) when condition X is changed as follows: ...?'"
    )
    perturbed_variable_name: str
    ground_truth_summary: str = Field(
        description="What ACTUALLY happened in the held-out paper (hidden from the agent during prediction)"
    )
    ground_truth_observables: List[ObservablePredictionItem] = Field(
        description="Actual experimental outcomes reported in the held-out paper for grading"
    )
    ground_truth_mechanism_explained_by_authors: str = Field(
        description="The mechanistic explanation given by the authors of the held-out paper"
    )


class AblationEvaluationScore(BaseModel):
    method_name: str
    directional_accuracy_percent: float = Field(
        ge=0.0, le=100.0, description="Percentage of target observables whose direction (increase/decrease/non-monotonic) matched the held-out paper"
    )
    primary_volume_or_morphology_correct: bool = Field(
        description="Did the agent accurately predict the main outcome highlighted in the held-out paper?"
    )
    mechanistic_alignment_score: int = Field(
        ge=1, le=10, description="1-10 score measuring how closely the agent's physical chemistry mechanism matches the held-out paper's verified mechanism"
    )
    quantitative_closeness_score: int = Field(
        ge=1, le=10, description="1-10 score for quantitative/regime accuracy"
    )
    brier_calibration_error: float = Field(
        description="Squared error between confidence (0-1) and binary correctness (0 or 1); lower is better"
    )
    critique_of_prediction: str = Field(
        description="Detailed explanation of what this agent configuration got right, what it missed, and whether cross-questioning fixed any errors"
    )
