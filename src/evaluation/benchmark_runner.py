"""End-to-End Ablation & Benchmark Runner for Literature Gap Analysis and Held-Out Experiment Prediction."""

import json
from pathlib import Path
from typing import Dict, Any, List

from src.llm.gemini_client import GeminiLLMClient
from src.ingestion.pdf_extractor import PDFPaperIngestor, SI_PATTERNS
from src.ingestion.literature_snowball import LiteratureSnowballEngine
from src.knowledge_base.hybrid_kb import HybridMechanisticKB
from src.agents.gap_discovery import LiteratureGapDiscoveryEngine
from src.agents.experiment_predictor import ExperimentPredictorEngine
from src.models.schemas import (
    BlindedHeldOutBenchmarkCase,
    ExperimentPredictionResult,
    AblationEvaluationScore,
)


class PerturbMatBenchmarkRunner:
    """Orchestrates seed + SI ingestion, anti-leakage snowball expansion, CMO graph construction,
    and head-to-head evaluation of Single-Agent vs. Cross-Questioning Agents.
    """

    def __init__(
        self,
        workspace_root: Path,
        model_name: str = "gemini-3.8-flash",
    ):
        self.root = workspace_root
        self.seed_dir = self.root / "data" / "seed_papers"
        self.held_out_dir = self.root / "data" / "held_out_papers"
        self.expanded_dir = self.root / "data" / "expanded_papers"
        self.outputs_dir = self.root / "outputs"
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

        self.llm = GeminiLLMClient(default_model=model_name)
        self.ingestor = PDFPaperIngestor(
            self.llm, cache_dir=self.outputs_dir / "extraction_cache"
        )

    def prepare_held_out_cases(self) -> List[BlindedHeldOutBenchmarkCase]:
        """Extract blinded benchmark prompts and isolated ground-truth outcomes from `data/held_out_papers/`."""
        if not self.held_out_dir.exists():
            return []
        all_files = sorted(
            [p for p in self.held_out_dir.glob("*") if p.suffix.lower() in {".pdf", ".docx"}]
        )
        main_pdfs = [
            p for p in all_files if p.suffix.lower() == ".pdf" and not SI_PATTERNS.search(p.stem)
        ]
        si_files = [
            p for p in all_files if p.suffix.lower() == ".docx" or SI_PATTERNS.search(p.stem)
        ]
        si_subdir = self.held_out_dir / "supplementary_info"
        if si_subdir.exists():
            si_files.extend(
                sorted([p for p in si_subdir.glob("*") if p.suffix.lower() in {".pdf", ".docx"}])
            )

        cases: List[BlindedHeldOutBenchmarkCase] = []
        for m_pdf in main_pdfs:
            cache_file = self.outputs_dir / "extraction_cache" / f"held_out_{m_pdf.stem}.json"
            if cache_file.exists():
                cases.append(BlindedHeldOutBenchmarkCase.model_validate_json(cache_file.read_text()))
            else:
                case = self.ingestor.extract_held_out_benchmark_case(m_pdf, si_files)
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(case.model_dump_json(indent=2))
                cases.append(case)
        return cases

    def build_knowledge_base(
        self,
        held_out_cases: List[BlindedHeldOutBenchmarkCase],
        enable_snowball_expansion: bool = True,
        max_snowball_papers: int = 12,
    ) -> tuple[HybridMechanisticKB, LiteratureSnowballEngine]:
        """Ingest seed papers + SIs and expand via OpenAlex/EuropePMC while strictly blocking held-out papers."""
        paired_seeds = self.ingestor.pair_main_and_si_pdfs(self.seed_dir)
        seed_extractions = []
        all_chunks = []

        print(f"[1/4] Loading/Ingesting {len(paired_seeds)} seed papers + paired SI files...", flush=True)
        for idx, (main_pdf, si_pdfs) in enumerate(paired_seeds, 1):
            cache_exists = (self.outputs_dir / "extraction_cache" / f"{main_pdf.stem}_extraction.json").exists()
            status_tag = "Loaded from disk cache (0 LLM calls)" if cache_exists else "Extracting via LLM"
            print(f"  -> [{idx}/{len(paired_seeds)}] {main_pdf.name} (+ {len(si_pdfs)} SI): {status_tag}", flush=True)
            ext, chunks = self.ingestor.extract_structured_paper(main_pdf, si_pdfs)
            seed_extractions.append(ext)
            all_chunks.extend(chunks)

        # Configure anti-leakage blacklists from held-out papers
        blacklisted_dois = {c.doi for c in held_out_cases if c.doi}
        blacklisted_titles = {c.title for c in held_out_cases if c.title}
        years = [c.publication_year for c in held_out_cases if c.publication_year]
        max_year = min(years) if years else None
        print(f"[2/4] Anti-Leakage Filter active: blocking held-out DOIs={blacklisted_dois}, max_year<{max_year}", flush=True)

        snowball = LiteratureSnowballEngine(
            llm_client=self.llm,
            expanded_dir=self.expanded_dir,
            blacklisted_dois=blacklisted_dois,
            blacklisted_titles=blacklisted_titles,
            max_publication_year=max_year,
        )

        expanded_extractions = []
        expanded_chunks = []
        if enable_snowball_expansion and seed_extractions:
            domain_topic = seed_extractions[0].core_system_studied or "gold nanobipyramid seed-mediated synthesis"
            print(f"  -> Running Citation & Mechanistic Snowball Expansion (up to {max_snowball_papers} external papers)...", flush=True)
            expanded_extractions, expanded_chunks = snowball.snowball_from_seed_extractions(
                seed_extractions=seed_extractions,
                domain_topic=domain_topic,
                max_new_papers=max_snowball_papers,
            )
            print(f"  -> Added {len(expanded_extractions)} external foundational/mechanistic papers to KB.", flush=True)
        elif self.expanded_dir.exists():
            from src.models.schemas import PaperExtraction
            from src.ingestion.pdf_extractor import PDFDocumentChunk
            for ep_file in sorted(self.expanded_dir.glob("*.json")):
                try:
                    ext = PaperExtraction.model_validate_json(ep_file.read_text())
                    expanded_extractions.append(ext)
                    expanded_chunks.append(
                        PDFDocumentChunk(
                            chunk_id=f"{ext.paper_id}_cached",
                            paper_id=ext.paper_id,
                            text=f"[Expanded Literature: {ext.title} ({ext.publication_year})]\n{ext.core_system_studied}",
                            is_si=False,
                            page_num=1,
                        )
                    )
                except Exception:
                    pass

        kb = HybridMechanisticKB(llm_client=self.llm)
        print("  -> Building in-memory CMO Causal Perturbation Graph & Chunk Store...", flush=True)
        kb.add_papers_and_chunks(
            extractions=seed_extractions + expanded_extractions,
            chunks=all_chunks + expanded_chunks,
            compute_embeddings=False,
        )
        kb.export_graph_json(self.outputs_dir / "cmo_knowledge_graph.json")
        return kb, snowball

    def score_prediction_against_held_out(
        self,
        method_name: str,
        prediction: ExperimentPredictionResult,
        ground_truth: BlindedHeldOutBenchmarkCase,
    ) -> AblationEvaluationScore:
        """Grade an agent's blinded prediction against the actual experimental results from the held-out paper."""
        system_instruction = (
            "You are an impartial Materials Science Benchmark Evaluator. "
            "Compare the AI agent's blinded prediction against the actual Ground-Truth experimental outcome from the held-out paper. "
            "Compute Directional Accuracy (0-100%), whether the primary volume/morphology trend was correct, "
            "Mechanistic Alignment (1-10), Quantitative Closeness (1-10), and Brier calibration error."
        )
        prompt = (
            f"### Method Evaluated: {method_name}\n\n"
            f"### Held-Out Paper Ground Truth:\n"
            f"- Title: {ground_truth.title}\n"
            f"- Perturbation Question: {ground_truth.perturbation_question}\n"
            f"- Actual Outcome Summary: {ground_truth.ground_truth_summary}\n"
            f"- Actual Observables: {json.dumps([o.model_dump() for o in ground_truth.ground_truth_observables], indent=2)}\n"
            f"- Authors' Verified Mechanism: {ground_truth.ground_truth_mechanism_explained_by_authors}\n\n"
            f"### Agent's Blinded Prediction:\n"
            f"{prediction.model_dump_json(indent=2)}\n\n"
            "Return the structured AblationEvaluationScore."
        )
        score = self.llm.generate_structured(
            prompt=prompt,
            schema_cls=AblationEvaluationScore,
            system_instruction=system_instruction,
        )
        score.method_name = method_name
        return score

    def run_full_ablation_study(self, max_snowball_papers: int = 10) -> Dict[str, Any]:
        """Run both Task 1 (Gap Discovery comparison) and Task 2 (4-way Experiment Prediction ablation on held-out papers)."""
        print("[0/4] Preparing Blinded Held-Out Benchmark Case from data/held_out_papers/...", flush=True)
        held_out_cases = self.prepare_held_out_cases()
        kb, snowball = self.build_knowledge_base(
            held_out_cases=held_out_cases,
            enable_snowball_expansion=True,
            max_snowball_papers=max_snowball_papers,
        )

        # Task 1: Literature Gap Analysis (Single-Agent vs. Cross-Questioning Agent)
        print("[3/4] Running Task 1: Literature Gap Discovery (Single-Agent vs. Adversarial Cross-Questioning)...", flush=True)
        gap_engine = LiteratureGapDiscoveryEngine(self.llm, kb, snowball)
        single_agent_gaps = gap_engine.discover_gaps_single_agent()
        cross_q_gaps, gap_debate_cycle = gap_engine.discover_gaps_with_cross_questioning()

        # Task 2: Held-Out Experiment Outcome Prediction across 4 Ablation Modes
        print("[4/4] Running Task 2: 4-Way Held-Out Experiment Prediction Ablation...", flush=True)
        pred_engine = ExperimentPredictorEngine(self.llm, kb, snowball)
        held_out_results = []

        for case in held_out_cases:
            print(f"  -> Predicting Held-Out Case: {case.held_out_paper_id}...", flush=True)
            print("     * Mode 1: Single-Agent Standard RAG", flush=True)
            p1 = pred_engine.predict_single_agent_rag(
                case.blinded_baseline_protocol, case.perturbation_question
            )
            s1 = self.score_prediction_against_held_out("1. Single-Agent Standard RAG", p1, case)

            print("     * Mode 2: Single-Agent + Hybrid CMO Graph KB", flush=True)
            p2 = pred_engine.predict_single_agent_hybrid_kb(
                case.blinded_baseline_protocol, case.perturbation_question
            )
            s2 = self.score_prediction_against_held_out("2. Single-Agent + Hybrid CMO Graph KB", p2, case)

            print("     * Mode 3: Generic Multi-Agent Discussion", flush=True)
            p3 = pred_engine.predict_generic_multi_agent(
                case.blinded_baseline_protocol, case.perturbation_question
            )
            s3 = self.score_prediction_against_held_out("3. Generic Multi-Agent Discussion", p3, case)

            print("     * Mode 4: Mechanistic Cross-Questioning Agent (Ours)", flush=True)
            p4, debate_cycle, search_logs = pred_engine.predict_with_mechanistic_cross_questioning(
                case.blinded_baseline_protocol, case.perturbation_question
            )
            s4 = self.score_prediction_against_held_out(
                "4. Mechanistic Cross-Questioning Agent (Ours)", p4, case
            )

            held_out_results.append(
                {
                    "held_out_case": case.model_dump(),
                    "predictions": {
                        "single_agent_rag": p1.model_dump(),
                        "single_agent_hybrid_kb": p2.model_dump(),
                        "generic_multi_agent": p3.model_dump(),
                        "mechanistic_cross_questioning": p4.model_dump(),
                    },
                    "cross_questioning_cycle": debate_cycle.model_dump(),
                    "triggered_external_searches": search_logs,
                    "scores": [s1.model_dump(), s2.model_dump(), s3.model_dump(), s4.model_dump()],
                }
            )

        summary_payload = {
            "num_seed_and_expanded_papers": len(kb.papers),
            "num_cmo_edges": kb.graph.number_of_edges(),
            "single_agent_gaps": single_agent_gaps.model_dump(),
            "cross_questioning_gaps": cross_q_gaps.model_dump(),
            "gap_cross_questioning_cycle": gap_debate_cycle.model_dump(),
            "held_out_evaluations": held_out_results,
            "external_sources_retrieved": snowball.retrieved_sources_log,
        }

        out_json = self.outputs_dir / "benchmark_results.json"
        out_json.write_text(json.dumps(summary_payload, indent=2))
        self._write_markdown_report(summary_payload, self.outputs_dir / "ablation_report.md")
        return summary_payload

    def _write_markdown_report(self, data: Dict[str, Any], report_path: Path) -> None:
        lines = [
            "# PerturbMat-Agent: Literature Gap & Experiment Prediction Ablation Report",
            "",
            f"- **Total Papers in Hybrid KB (Seed + Snowball Expanded):** {data['num_seed_and_expanded_papers']}",
            f"- **Total Condition-Mechanism-Outcome (CMO) Causal Edges:** {data['num_cmo_edges']}",
            "",
            "---",
            "## Part 1: Literature Gap Analysis (Single-Agent vs. Cross-Questioning Agent)",
            "",
            "### Cross-Questioning Refinements to Gap Quality:",
        ]
        for ref in data["cross_questioning_gaps"].get("cross_questioning_refinements") or []:
            lines.append(f"- {ref}")

        lines.append("\n### Top Mechanistic & Parameter-Space Gaps Identified (Post Cross-Questioning):")
        for g in data["cross_questioning_gaps"].get("gaps", []):
            lines.extend(
                [
                    f"#### [{g['gap_id']}] {g['title']} (`{g['gap_category']}` | Specificity: {g['specificity_score']}/10)",
                    f"- **Parameter Coordinates:** {', '.join(g['parameter_coordinates'])}",
                    f"- **Corpus Evidence:** {g['evidence_from_corpus']}",
                    f"- **Competing Hypotheses:** {'; '.join(g['competing_mechanistic_hypotheses'])}",
                    f"- **Decisive Experiment:** {g['proposed_decisive_experiment']}",
                    "",
                ]
            )

        lines.extend(
            [
                "---",
                "## Part 2: Held-Out Paper Counterfactual Experiment Prediction Benchmark",
                "",
            ]
        )
        for item in data.get("held_out_evaluations", []):
            case = item["held_out_case"]
            lines.extend(
                [
                    f"### Held-Out Paper: *{case['title']}* ({case.get('publication_year')})",
                    f"- **Blinded Perturbation Question:** {case['perturbation_question']}",
                    f"- **Actual Experimental Outcome (Ground Truth):** {case['ground_truth_summary']}",
                    "",
                    "| Architecture | Primary Trend Correct? | Directional Acc (%) | Mechanistic Alignment (1-10) | Quant. Closeness (1-10) | Brier Error (↓) |",
                    "| :--- | :---: | :---: | :---: | :---: | :---: |",
                ]
            )
            for sc in item["scores"]:
                lines.append(
                    f"| **{sc['method_name']}** | {'✅ Yes' if sc['primary_volume_or_morphology_correct'] else '❌ No'} | "
                    f"{sc['directional_accuracy_percent']:.1f}% | {sc['mechanistic_alignment_score']}/10 | "
                    f"{sc['quantitative_closeness_score']}/10 | {sc['brier_calibration_error']:.3f} |"
                )
            lines.append("")

        if data.get("external_sources_retrieved"):
            lines.extend(["---", "## External Literature Sources Consulted (OpenAlex / EuropePMC)", ""])
            for src in data["external_sources_retrieved"]:
                lines.append(f"- {src.get('title')} ({src.get('year')}): {src.get('url')}")

        report_path.write_text("\n".join(lines))
