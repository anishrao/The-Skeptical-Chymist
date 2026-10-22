"""Literature Gap Discovery Engine comparing Single-Agent vs. Adversarial Cross-Questioning Gap Analysis."""

import json
from typing import Optional, Tuple
from src.llm.gemini_client import GeminiLLMClient
from src.knowledge_base.hybrid_kb import HybridMechanisticKB
from src.ingestion.literature_snowball import LiteratureSnowballEngine
from src.models.schemas import LiteratureGapReport, CrossQuestioningCycle


class LiteratureGapDiscoveryEngine:
    """Discovers parameter-space holes and mechanistic contradictions across research papers,
    with optional adversarial cross-questioning + live literature verification to eliminate trivial or already-solved gaps.
    """

    def __init__(
        self,
        llm_client: GeminiLLMClient,
        kb: HybridMechanisticKB,
        snowball: Optional[LiteratureSnowballEngine] = None,
    ):
        self.llm = llm_client
        self.kb = kb
        self.snowball = snowball

    def _build_corpus_matrix_context(self) -> str:
        coverage = self.kb.compute_parameter_space_coverage_matrix()
        contradictions = self.kb.find_mechanistic_contradictions()
        cmo_summary = self.kb.query_cmo_subgraph_summary("bipyramid volume aspect ratio yield mechanism")

        paper_summaries = []
        for pid, ext in self.kb.papers.items():
            paper_summaries.append(
                f"- {pid} ({ext.publication_year}): '{ext.title}' | Varied: {ext.parameters_varied} | "
                f"Constant: {ext.parameters_held_constant} | Untested assumptions: {ext.untested_assumptions_or_limitations}"
            )

        return (
            "### Ingested Papers & Tested Regimes:\n"
            + "\n".join(paper_summaries)
            + "\n\n### Algorithmic Parameter-Space Coverage Matrix:\n"
            + json.dumps(coverage, indent=2)
            + "\n\n### Algorithmic Contradictions Detected Across Papers:\n"
            + json.dumps(contradictions, indent=2)
            + "\n\n"
            + cmo_summary
        )

    def discover_gaps_single_agent(self) -> LiteratureGapReport:
        """Baseline Single-Agent gap discovery over the Hybrid KB."""
        context = self._build_corpus_matrix_context()
        system_instruction = (
            "You are a senior materials science research strategist. "
            "Identify concrete, non-trivial gaps in the literature based strictly on the Parameter-Space Coverage Matrix "
            "and Condition-Mechanism-Outcome (CMO) contradictions. "
            "NEVER output generic platitudes like 'scale up synthesis' or 'use green solvents'. "
            "Every gap must specify exact synthesis parameter coordinates, competing physical mechanisms, and a decisive wet-lab experiment."
        )
        prompt = (
            "Analyze the following corpus synthesis matrix and CMO causal graph to produce a structured LiteratureGapReport "
            "with 4 to 6 high-value experimental gaps:\n\n"
            f"{context}"
        )
        return self.llm.generate_structured(
            prompt=prompt,
            schema_cls=LiteratureGapReport,
            system_instruction=system_instruction,
        )

    def discover_gaps_with_cross_questioning(self) -> Tuple[LiteratureGapReport, CrossQuestioningCycle]:
        """Two-stage adversarial Cross-Questioning Gap Discovery:
        1. Proposer drafts candidate parameter-space holes & mechanistic contradictions.
        2. Skeptic Critic cross-examines each gap (checking if external literature already solved it,
           if the regime is chemically unfeasible, or if variables are confounded) and triggers OpenAlex/EuropePMC searches.
        3. Arbiter refines and filters the gaps into a high-specificity LiteratureGapReport.
        """
        initial_report = self.discover_gaps_single_agent()
        context = self._build_corpus_matrix_context()

        critic_system = (
            "You are a ruthless physical chemistry & nanomaterial synthesis peer-reviewer. "
            "Critique the Proposer's candidate literature gaps. Attack:\n"
            "1. Gaps that might already be resolved in broader literature outside the initial seed set (provide `external_search_query_needed`).\n"
            "2. Confounded variables (e.g., changing HAuCl4 or AgNO3 without accounting for stoichiometric Br-/Au3+ or seed-to-Au3+ mass balance).\n"
            "3. Chemically trivial regimes (e.g., surfactant precipitation or complete loss of seed twinning).\n"
            "Formulate 3-4 sharp cross-questioning challenges."
        )
        critic_prompt = (
            f"Corpus Context:\n{context}\n\n"
            f"Candidate Literature Gaps Proposed:\n{initial_report.model_dump_json(indent=2)}\n\n"
            "Generate your CrossQuestioningCycle challenges."
        )
        cycle = self.llm.generate_structured(
            prompt=critic_prompt,
            schema_cls=CrossQuestioningCycle,
            system_instruction=critic_system,
        )

        # Execute live external literature verification for any search queries requested by the Critic
        external_verification_notes = []
        if self.snowball:
            for ch in cycle.challenges:
                if ch.external_search_query_needed:
                    hits = self.snowball.search_literature(ch.external_search_query_needed, max_results=3)
                    for h in hits:
                        source_engine = h.get("source", "Literature")
                        external_verification_notes.append(
                            f"[{source_engine.upper()} | Query: {ch.external_search_query_needed}] Found external paper: "
                            f"{h['title']} ({h.get('publication_year')}) - Abstract snippet: {h.get('abstract', '')[:400]}"
                        )

            # Check publication activity trends via Valency to distinguish dead ends from emerging frontiers
            if getattr(self.snowball, "valency", None) and cycle.challenges:
                try:
                    q_concept = cycle.challenges[0].external_search_query_needed or "gold nanobipyramid facet mechanism"
                    trends = self.snowball.valency.get_keyword_trends(q_concept[:50])
                    if trends and "results" in trends:
                        external_verification_notes.append(
                            f"[VALENCY TREND RADAR] Concept '{q_concept[:50]}' publication trajectory: "
                            f"{str(trends.get('results', {}))[:200]}"
                        )
                except Exception:
                    pass

        arbiter_system = (
            "You are the Synthesis Arbiter. Using the Critic's cross-questioning challenges and the newly retrieved "
            "external literature checks, prune or sharpen the initial candidate gaps. "
            "If an external paper already explored a proposed gap, narrow the gap to the exact unresolved mechanistic regime. "
            "Populate `cross_questioning_refinements` with explicit bullet points explaining how cross-questioning improved each gap."
        )
        arbiter_prompt = (
            f"Corpus Context:\n{context}\n\n"
            f"Initial Candidate Gaps:\n{initial_report.model_dump_json(indent=2)}\n\n"
            f"Critic Cross-Questioning Challenges:\n{cycle.model_dump_json(indent=2)}\n\n"
            f"External Literature Verification Results:\n"
            + ("\n".join(external_verification_notes) if external_verification_notes else "No external hits contradicted the gaps.")
            + "\n\nProduce the final refined LiteratureGapReport."
        )
        final_report = self.llm.generate_structured(
            prompt=arbiter_prompt,
            schema_cls=LiteratureGapReport,
            system_instruction=arbiter_system,
        )
        return final_report, cycle
