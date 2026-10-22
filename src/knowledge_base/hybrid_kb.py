"""Hybrid Mechanistic Knowledge Base combining a Condition-Mechanism-Outcome (CMO) Causal Graph,
a Parameter-Space Co-Variation Matrix, and a Dense+Lexical Vector Store over Main + SI chunks.
"""

import re
import json
from pathlib import Path
from itertools import combinations
from typing import List, Dict, Optional, Tuple, Any
import numpy as np
import networkx as nx

from src.llm.gemini_client import GeminiLLMClient
from src.models.schemas import PaperExtraction, CMOPerturbationEdge
from src.ingestion.pdf_extractor import PDFDocumentChunk


def canonicalize_term(term: str) -> str:
    """Normalize parameter and observable names so related concepts merge in the CMO graph."""
    t = term.strip().lower()
    synonyms = {
        r"(agno3|silver nitrate|ag\+|silver ion).*": "AgNO3 / [Ag+] concentration",
        r"(haucl4|gold precursor|au3\+|aucl4).*": "HAuCl4 / [Au3+] concentration",
        r"(hcl|hydrochloric acid|ph|acid).*": "HCl / pH",
        r"(ctab|cetyltrimethylammonium bromide).*": "CTAB surfactant concentration",
        r"(ctac|cetyltrimethylammonium chloride).*": "CTAC surfactant concentration",
        r"(ascorbic acid|aa|reducing agent).*": "Ascorbic acid (AA) concentration",
        r"(seed|pentatwinned seed).*": "Seed concentration / volume",
        r"(temp|temperature).*": "Reaction temperature",
        r"(nabr|kbr|bromide|br\-).*": "Bromide (Br-) additive",
        r".*(volume|particle volume|bipyramid volume).*": "Bipyramid single-particle volume",
        r".*(aspect ratio|ar|length to width).*": "Aspect ratio (AR)",
        r".*(lspr|plasmon|wavelength|peak).*": "Longitudinal LSPR peak wavelength",
        r".*(length|tip-to-tip).*": "Bipyramid longitudinal length",
        r".*(width|equatorial|diameter).*": "Bipyramid equatorial width",
        r".*(yield|purity|monodispersity).*": "Bipyramid shape yield / purity",
        r".*(tip|sharpness|truncation).*": "Tip sharpness / truncation",
    }
    for pattern, replacement in synonyms.items():
        if re.match(pattern, t):
            return replacement
    return term.strip()


class HybridMechanisticKB:
    """Dual-layer Knowledge Base:
    1. Condition-Mechanism-Outcome (CMO) Directed Multigraph (`nx.MultiDiGraph`)
    2. Parameter-Space Co-Variation Matrix
    3. Hybrid Vector + Lexical Chunk Store (`gemini-embedding-2` + keyword scoring)
    """

    def __init__(self, llm_client: Optional[GeminiLLMClient] = None):
        self.llm = llm_client
        self.graph = nx.MultiDiGraph()
        self.papers: Dict[str, PaperExtraction] = {}
        self.chunks: List[PDFDocumentChunk] = []
        self.chunk_embeddings: Optional[np.ndarray] = None

    def enrich_missing_cmo_edges_in_batch(
        self,
        extractions: List[PaperExtraction],
        chunks: List[PDFDocumentChunk],
        cache_dir: Optional[Path] = None,
    ) -> None:
        """If any cached PaperExtraction has 0 CMO edges, enrich all of them in a single batched LLM call
        and persist the enriched cmo_edges back to disk cache so future runs need 0 extra calls.
        """
        missing = [ext for ext in extractions if not ext.cmo_edges]
        if not missing or self.llm is None:
            return

        from pydantic import BaseModel as _BM

        class _PaperCMOItem(_BM):
            paper_id: str
            parameters_varied: List[str]
            cmo_edges: List[CMOPerturbationEdge]

        class _BatchCMOEnrichment(_BM):
            papers: List[_PaperCMOItem]

        chunks_by_paper: Dict[str, List[PDFDocumentChunk]] = {}
        for c in chunks:
            chunks_by_paper.setdefault(c.paper_id, []).append(c)

        prompt_parts: List[str] = []
        for ext in missing:
            p_chunks = chunks_by_paper.get(ext.paper_id, [])
            # Sample intro, middle results, and SI chunks so experimental tables/trends are captured
            selected_c = []
            if p_chunks:
                selected_c.append(p_chunks[0])
                if len(p_chunks) > 3:
                    selected_c.append(p_chunks[len(p_chunks) // 3])
                if len(p_chunks) > 6:
                    selected_c.append(p_chunks[(2 * len(p_chunks)) // 3])
                si_c = [c for c in p_chunks if c.is_si]
                if si_c:
                    selected_c.append(si_c[0])
            sample_text = "\n".join(c.text[:900] for c in selected_c[:4])
            runs_summary = ""
            if ext.synthesis_runs:
                runs_summary = "Synthesis Runs Extracted: " + "; ".join(
                    f"{r.run_id}: {[f'{p.name}={p.raw_value}' for p in r.parameters[:5]]} -> "
                    f"morphology={r.outcome.morphology}, L={r.outcome.length_nm}, W={r.outcome.width_nm}, AR={r.outcome.aspect_ratio}, LSPR={r.outcome.lspr_peak_nm}, Vol={r.outcome.volume_nm3}"
                    for r in ext.synthesis_runs[:5]
                )
            limits = "; ".join(ext.untested_assumptions_or_limitations[:3])
            prompt_parts.append(
                f"=== PAPER_ID: {ext.paper_id} | TITLE: {ext.title} ({ext.publication_year}) ===\n"
                f"Core System: {ext.core_system_studied}\n"
                f"{runs_summary}\n"
                f"Limitations/Notes: {limits}\n"
                f"Excerpts:\n{sample_text[:2400]}"
            )

        print(
            f"  [CMO Graph Enricher] Synthesizing directional CMO causal edges for {len(missing)} papers in 1 batched LLM call...",
            flush=True,
        )
        try:
            batch_res = self.llm.generate_structured(
                prompt=(
                    "For EACH paper below, extract 2 to 4 directional Condition-Mechanism-Outcome (CMO) perturbation edges "
                    "(perturbed_parameter -> proposed_mechanism -> affected_observable with fixed_boundary_conditions and quantitative_effect) "
                    "and list the standardized parameters_varied.\n\n"
                    + "\n\n".join(prompt_parts)
                ),
                schema_cls=_BatchCMOEnrichment,
                system_instruction=(
                    "You are a physical chemistry & gold nanobipyramid synthesis expert. "
                    "Ensure every paper_id receives accurate directional CMO edges (covering parameters like AgNO3 concentration, "
                    "CTAB concentration, CTAC/CTAB ratio, HCl/pH, 8-HQL or ascorbic acid reducing agent, seed thermal treatment, "
                    "temperature, and observables like Aspect ratio, Longitudinal LSPR peak wavelength, Bipyramid single-particle volume, "
                    "Bipyramid longitudinal length, Bipyramid equatorial width, Shape yield)."
                ),
            )
            by_id = {item.paper_id: item for item in batch_res.papers}
            if cache_dir is None:
                cache_dir = Path(__file__).resolve().parents[2] / "outputs" / "extraction_cache"
            expanded_dir = Path(__file__).resolve().parents[2] / "data" / "expanded_papers"
            for ext in missing:
                matched = by_id.get(ext.paper_id)
                if matched and matched.cmo_edges:
                    ext.cmo_edges = matched.cmo_edges
                    if matched.parameters_varied:
                        ext.parameters_varied = matched.parameters_varied
                    # Save back to cache
                    c_path = cache_dir / f"{ext.paper_id}_extraction.json"
                    e_path = expanded_dir / f"{ext.paper_id}.json"
                    if c_path.exists():
                        c_path.write_text(ext.model_dump_json(indent=2))
                    elif e_path.exists():
                        e_path.write_text(ext.model_dump_json(indent=2))
        except Exception as e:
            print(f"  [CMO Graph Enricher Warning: {e}]", flush=True)

    def add_papers_and_chunks(
        self,
        extractions: List[PaperExtraction],
        chunks: List[PDFDocumentChunk],
        compute_embeddings: bool = True,
    ) -> None:
        """Populate the CMO causal graph, parameter matrix, and vector store."""
        self.enrich_missing_cmo_edges_in_batch(extractions, chunks)
        for ext in extractions:
            if not ext.parameters_varied:
                derived_params = [edge.perturbed_parameter for edge in ext.cmo_edges]
                for r in ext.synthesis_runs:
                    for p in r.parameters:
                        if p.role in ("silver_additive", "surfactant", "halide_additive", "reducing_agent", "pH_modifier", "temperature", "seed_parameter"):
                            derived_params.append(p.name)
                ext.parameters_varied = list(dict.fromkeys(derived_params))[:6]
            self.papers[ext.paper_id] = ext
            for edge in ext.cmo_edges:
                u = canonicalize_term(edge.perturbed_parameter)
                v = canonicalize_term(edge.affected_observable)
                self.graph.add_node(u, node_type="parameter", label=u)
                self.graph.add_node(v, node_type="observable", label=v)
                self.graph.add_edge(
                    u,
                    v,
                    paper_id=ext.paper_id,
                    paper_title=ext.title,
                    publication_year=ext.publication_year,
                    raw_parameter=edge.perturbed_parameter,
                    raw_observable=edge.affected_observable,
                    perturbation_direction=edge.perturbation_direction,
                    parameter_range=edge.parameter_range_tested,
                    boundary_conditions=edge.fixed_boundary_conditions,
                    mechanism=edge.proposed_mechanism,
                    outcome_direction=edge.outcome_direction,
                    quantitative_effect=edge.quantitative_effect,
                    evidence_quote=edge.evidence_quote,
                    from_si=edge.from_supplementary_info,
                )

        self.chunks.extend(chunks)
        if compute_embeddings and self.llm and self.chunks:
            emb_cache = Path(__file__).resolve().parents[2] / "outputs" / "extraction_cache" / f"embeddings_{len(self.chunks)}.npy"
            if emb_cache.exists():
                try:
                    self.chunk_embeddings = np.load(str(emb_cache))
                    return
                except Exception:
                    pass
            try:
                texts = [c.text[:2000] for c in self.chunks]
                emb_list = self.llm.embed_texts(texts, output_dimensionality=768)
                arr = np.array(emb_list, dtype=np.float32)
                norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
                self.chunk_embeddings = arr / norms
                emb_cache.parent.mkdir(parents=True, exist_ok=True)
                np.save(str(emb_cache), self.chunk_embeddings)
            except Exception as e:
                print(f"  [Warning: dense embedding fallback to lexical BM25 due to: {e}]", flush=True)
                self.chunk_embeddings = None

    def retrieve_chunks(
        self, query: str, top_k: int = 8, seed_papers_only: bool = False
    ) -> List[PDFDocumentChunk]:
        """Hybrid dense (`gemini-embedding-2`) + lexical retrieval over Main and SI chunks."""
        if not self.chunks:
            return []

        candidate_indices = [
            i
            for i, c in enumerate(self.chunks)
            if not (seed_papers_only and (c.paper_id.startswith("OA_") or c.paper_id.startswith("EPMC_")))
        ]
        if not candidate_indices:
            return []

        q_tokens = set(re.findall(r"[a-z0-9\+]+", query.lower()))
        lexical_scores = np.zeros(len(candidate_indices), dtype=np.float32)
        for idx_pos, chunk_idx in enumerate(candidate_indices):
            c_tokens = set(re.findall(r"[a-z0-9\+]+", self.chunks[chunk_idx].text.lower()))
            if q_tokens:
                lexical_scores[idx_pos] = len(q_tokens.intersection(c_tokens)) / len(q_tokens)

        dense_scores = np.zeros(len(candidate_indices), dtype=np.float32)
        if self.chunk_embeddings is not None and self.llm is not None:
            try:
                q_emb = np.array(self.llm.embed_texts([query], output_dimensionality=768)[0], dtype=np.float32)
                q_emb = q_emb / (np.linalg.norm(q_emb) + 1e-9)
                sub_matrix = self.chunk_embeddings[candidate_indices]
                dense_scores = sub_matrix @ q_emb
            except Exception:
                pass

        combined_scores = 0.65 * dense_scores + 0.35 * lexical_scores
        ranked_positions = np.argsort(-combined_scores)[:top_k]
        return [self.chunks[candidate_indices[pos]] for pos in ranked_positions]

    def find_mechanistic_contradictions(self) -> List[Dict[str, Any]]:
        """Detect pairs of CMO edges with the same (Parameter, Observable, Perturbation Direction)
        but conflicting Outcome Directions or Mechanisms across papers.
        """
        contradictions: List[Dict[str, Any]] = []
        for u, v in self.graph.edges():
            edge_dict = self.graph.get_edge_data(u, v)
            if not edge_dict or len(edge_dict) < 2:
                continue
            edges = list(edge_dict.values())
            for e1, e2 in combinations(edges, 2):
                if e1["paper_id"] == e2["paper_id"]:
                    continue
                if e1["perturbation_direction"] == e2["perturbation_direction"]:
                    if e1["outcome_direction"] != e2["outcome_direction"]:
                        contradictions.append(
                            {
                                "parameter": u,
                                "observable": v,
                                "perturbation_direction": e1["perturbation_direction"],
                                "paper_1": f"{e1['paper_id']} ({e1.get('publication_year')})",
                                "outcome_1": f"{e1['outcome_direction']} ({e1['quantitative_effect']})",
                                "mechanism_1": e1["mechanism"],
                                "boundary_1": e1["boundary_conditions"],
                                "paper_2": f"{e2['paper_id']} ({e2.get('publication_year')})",
                                "outcome_2": f"{e2['outcome_direction']} ({e2['quantitative_effect']})",
                                "mechanism_2": e2["mechanism"],
                                "boundary_2": e2["boundary_conditions"],
                            }
                        )
        # Deduplicate
        unique = []
        seen = set()
        for item in contradictions:
            key = (item["parameter"], item["observable"], item["paper_1"], item["paper_2"])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    def compute_parameter_space_coverage_matrix(self) -> Dict[str, Any]:
        """Analyze which synthesis parameters have been studied individually vs. co-varied together,
        surfacing concrete 2D parameter-space holes.
        """
        param_to_papers: Dict[str, Set[str]] = {}
        for pid, ext in self.papers.items():
            varied = {canonicalize_term(p) for p in ext.parameters_varied}
            for e in ext.cmo_edges:
                varied.add(canonicalize_term(e.perturbed_parameter))
            for p in varied:
                param_to_papers.setdefault(p, set()).add(pid)

        sorted_params = sorted(param_to_papers.keys(), key=lambda k: len(param_to_papers[k]), reverse=True)
        co_varied_pairs: List[Dict[str, Any]] = []
        unexplored_pairs: List[Dict[str, Any]] = []

        for p1, p2 in combinations(sorted_params[:12], 2):
            shared = param_to_papers[p1].intersection(param_to_papers[p2])
            if shared:
                co_varied_pairs.append(
                    {"pair": (p1, p2), "papers_co_varying": sorted(shared)}
                )
            else:
                unexplored_pairs.append(
                    {
                        "pair": (p1, p2),
                        "p1_papers": sorted(param_to_papers[p1]),
                        "p2_papers": sorted(param_to_papers[p2]),
                    }
                )

        return {
            "parameter_frequency": {p: sorted(list(pids)) for p, pids in param_to_papers.items()},
            "co_varied_pairs": co_varied_pairs,
            "unexplored_parameter_intersections": unexplored_pairs,
        }

    def query_cmo_subgraph_summary(self, query_text: str) -> str:
        """Format all Condition-Mechanism-Outcome (CMO) edges relevant to a query into a structured mechanistic briefing."""
        canonical_q = canonicalize_term(query_text)
        q_words = set(re.findall(r"[a-z0-9\+]+", query_text.lower()))

        matched_edges: List[str] = []
        all_edges: List[str] = []

        for u, v, data in self.graph.edges(data=True):
            edge_str = (
                f"- [{data['paper_id']} ({data.get('publication_year')}, {'SI' if data.get('from_si') else 'Main'})] "
                f"Perturbation: {u} ({data['perturbation_direction']}, range: {data['parameter_range']}) "
                f"| Boundary Conditions: {', '.join(data.get('boundary_conditions', []))} "
                f"--> Mechanism: {data['mechanism']} "
                f"--> Outcome on {v}: {data['outcome_direction']} ({data['quantitative_effect']})"
            )
            all_edges.append(edge_str)
            blob = f"{u} {v} {data['raw_parameter']} {data['raw_observable']} {data['mechanism']}".lower()
            if canonical_q.lower() in blob or len(q_words.intersection(set(re.findall(r"[a-z0-9\+]+", blob)))) >= 2:
                matched_edges.append(edge_str)

        selected = matched_edges if matched_edges else all_edges[:25]
        contradictions = self.find_mechanistic_contradictions()
        contra_text = ""
        if contradictions:
            contra_lines = [
                f"  * CONFLICT on {c['parameter']} -> {c['observable']}: {c['paper_1']} reports {c['outcome_1']} "
                f"(under {c['boundary_1']}), whereas {c['paper_2']} reports {c['outcome_2']} (under {c['boundary_2']})."
                for c in contradictions[:8]
            ]
            contra_text = "\n\n### Detected Mechanistic Contradictions / Regime Shifts in Graph:\n" + "\n".join(contra_lines)

        return (
            "### Condition-Mechanism-Outcome (CMO) Causal Graph Edges:\n"
            + ("\n".join(selected[:30]) if selected else "No CMO edges extracted yet.")
            + contra_text
        )

    def export_graph_json(self, output_path: Path) -> None:
        """Save the CMO graph and parameter coverage matrix to JSON for visualization and inspection."""
        nodes = [{"id": n, **self.graph.nodes[n]} for n in self.graph.nodes()]
        edges = [
            {"source": u, "target": v, **data}
            for u, v, data in self.graph.edges(data=True)
        ]
        payload = {
            "num_papers": len(self.papers),
            "num_chunks": len(self.chunks),
            "nodes": nodes,
            "edges": edges,
            "contradictions": self.find_mechanistic_contradictions(),
            "parameter_space_coverage": self.compute_parameter_space_coverage_matrix(),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2))
