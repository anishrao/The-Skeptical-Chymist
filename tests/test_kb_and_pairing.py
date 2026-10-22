"""Unit tests verifying SI PDF pairing, Anti-Leakage filtering, and CMO Knowledge Graph analytics."""

from pathlib import Path
from src.models.schemas import PaperExtraction, CMOPerturbationEdge
from src.knowledge_base.hybrid_kb import HybridMechanisticKB
from src.ingestion.literature_snowball import LiteratureSnowballEngine


def test_cmo_graph_contradiction_and_parameter_matrix():
    p1 = PaperExtraction(
        paper_id="Paper_2017_A",
        title="Control of Gold Nanobipyramid Aspect Ratio via AgNO3",
        authors_short="AuthorA et al.",
        publication_year=2017,
        core_system_studied="Gold bipyramids",
        parameters_varied=["AgNO3 concentration", "HCl concentration"],
        parameters_held_constant=["Temperature = 30 °C", "CTAB = 100 mM"],
        cmo_edges=[
            CMOPerturbationEdge(
                perturbed_parameter="AgNO3 concentration",
                perturbation_direction="increase",
                parameter_range_tested="0.02 - 0.10 mM",
                fixed_boundary_conditions=["CTAB = 100 mM", "T = 30 °C"],
                proposed_mechanism="Ag0 underpotential deposition stabilizes stepped {110} facets",
                affected_observable="Bipyramid single-particle volume",
                outcome_direction="decrease",
                quantitative_effect="Volume drops from 42,000 nm^3 to 19,000 nm^3 as longitudinal growth slows",
                evidence_quote="Increasing AgNO3 decreased average particle volume.",
                from_supplementary_info=False,
            )
        ],
    )

    p2 = PaperExtraction(
        paper_id="Paper_2020_B",
        title="High-Temperature Seed-Mediated Growth of Gold Bipyramids",
        authors_short="AuthorB et al.",
        publication_year=2020,
        core_system_studied="Gold bipyramids",
        parameters_varied=["AgNO3 concentration", "Reaction temperature"],
        parameters_held_constant=["CTAC/NaBr co-surfactant"],
        cmo_edges=[
            CMOPerturbationEdge(
                perturbed_parameter="AgNO3 concentration",
                perturbation_direction="increase",
                parameter_range_tested="0.05 - 0.25 mM",
                fixed_boundary_conditions=["CTAC = 100 mM", "T = 65 °C"],
                proposed_mechanism="At elevated temperature with CTAC, excess Ag+ accelerates overgrown tip deposition",
                affected_observable="Bipyramid single-particle volume",
                outcome_direction="increase",
                quantitative_effect="Volume increases from 20,000 nm^3 to 35,000 nm^3",
                evidence_quote="At 65 °C, higher Ag+ led to larger particle volumes.",
                from_supplementary_info=True,
            )
        ],
    )

    kb = HybridMechanisticKB(llm_client=None)
    kb.add_papers_and_chunks([p1, p2], chunks=[], compute_embeddings=False)

    contradictions = kb.find_mechanistic_contradictions()
    assert len(contradictions) == 1
    assert contradictions[0]["parameter"] == "AgNO3 / [Ag+] concentration"
    assert contradictions[0]["observable"] == "Bipyramid single-particle volume"

    matrix = kb.compute_parameter_space_coverage_matrix()
    unexplored = [item["pair"] for item in matrix["unexplored_parameter_intersections"]]
    assert ("HCl / pH", "Reaction temperature") in unexplored or (
        "Reaction temperature",
        "HCl / pH",
    ) in unexplored


def test_anti_leakage_filter(tmp_path: Path):
    snowball = LiteratureSnowballEngine(
        llm_client=None,  # type: ignore
        expanded_dir=tmp_path,
        blacklisted_dois={"https://doi.org/10.1021/acs.chemmater.5b99999"},
        blacklisted_titles={"Unexpected Volume Shrinkage in Gold Nanobipyramids Upon Halide Tuning"},
        max_publication_year=2024,
    )
    # Exact DOI match must be blocked
    assert snowball._is_leaked_or_blocked("Some Title", "10.1021/acs.chemmater.5b99999", 2022)
    # Exact/substring Title match must be blocked
    assert snowball._is_leaked_or_blocked(
        "Unexpected volume shrinkage in gold nanobipyramids upon halide tuning!", None, 2021
    )
    # Future publication year >= cutoff must be blocked
    assert snowball._is_leaked_or_blocked("Unrelated Earlier Paper", "10.1021/other", 2025)
    # Earlier foundational paper must be allowed
    assert not snowball._is_leaked_or_blocked(
        "Pentatwinned Gold Seeds for High-Yield Bipyramids", "10.1021/foundational2016", 2016
    )


if __name__ == "__main__":
    test_cmo_graph_contradiction_and_parameter_matrix()
    test_anti_leakage_filter(Path("/tmp"))
    print("All CMO Graph & Anti-Leakage unit tests passed!")
