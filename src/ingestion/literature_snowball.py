"""Dynamic Literature Expansion Engine (Citation Snowballing + Active Mechanistic Search) with Strict Anti-Leakage Filtering.
Uses isolated OS-level `curl` subprocesses with `--connect-timeout 4 --max-time 8` so external HTTP calls can never hang or lock Python's DNS resolver.
"""

import os
import re
import json
import subprocess
from urllib.parse import urlencode
from pathlib import Path
from typing import List, Dict, Optional, Set, Any
from dotenv import load_dotenv

from src.llm.gemini_client import GeminiLLMClient
from src.models.schemas import PaperExtraction
from src.ingestion.pdf_extractor import PDFDocumentChunk


def safe_curl_get_json(base_url: str, params: Dict[str, Any], max_time_s: int = 8) -> Optional[Dict]:
    """Execute HTTP GET in an isolated child `curl` process with hard connect & total timeouts."""
    query_str = urlencode({k: v for k, v in params.items() if v is not None})
    full_url = f"{base_url}?{query_str}" if query_str else base_url
    cmd = [
        "/usr/bin/curl",
        "-sL",
        "--connect-timeout",
        "4",
        "--max-time",
        str(max_time_s),
        "-H",
        "User-Agent: PerturbMatAgent/0.1 (mailto:research@opensource.science)",
        "-H",
        "Accept: application/json",
        full_url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max_time_s + 2,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
    except Exception:
        return None
    return None


class LiteratureSnowballEngine:
    """Expands the initial seed papers into a broader field corpus using OpenAlex & EuropePMC
    while enforcing strict temporal and DOI/title blacklists so the held-out test paper is never leaked.
    """

    def __init__(
        self,
        llm_client: GeminiLLMClient,
        expanded_dir: Path,
        blacklisted_dois: Optional[Set[str]] = None,
        blacklisted_titles: Optional[Set[str]] = None,
        max_publication_year: Optional[int] = None,
        valency_client: Optional[Any] = None,
    ):
        project_env = Path(__file__).resolve().parents[2] / ".env"
        if project_env.exists():
            load_dotenv(project_env, override=True)

        self.llm = llm_client
        self.expanded_dir = expanded_dir
        self.expanded_dir.mkdir(parents=True, exist_ok=True)
        self.blacklisted_dois = {self._norm_doi(d) for d in (blacklisted_dois or set()) if d}
        self.blacklisted_titles = {self._norm_title(t) for t in (blacklisted_titles or set()) if t}
        self.max_publication_year = max_publication_year
        raw_oa_key = os.environ.get("OPENALEX_API_KEY", "").strip().strip('"').strip("'")
        self.openalex_api_key = raw_oa_key or None
        self.retrieved_sources_log: List[Dict[str, str]] = []

        if valency_client is None:
            try:
                from src.knowledge_base.valency_client import ValencyClient
                self.valency = ValencyClient()
            except Exception:
                self.valency = None
        else:
            self.valency = valency_client

    @staticmethod
    def _norm_doi(doi: str) -> str:
        doi = doi.strip().lower()
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
        return doi

    @staticmethod
    def _norm_title(title: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", title.lower())

    @staticmethod
    def reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
        """Reconstruct abstract text from OpenAlex `abstract_inverted_index`."""
        if not inverted_index:
            return ""
        word_positions: List[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in word_positions)

    def _is_leaked_or_blocked(self, title: str, doi: Optional[str], pub_year: Optional[int]) -> bool:
        """Verify that a candidate external paper does not leak the held-out experiment."""
        if doi and self._norm_doi(doi) in self.blacklisted_dois:
            return True
        if title:
            nt = self._norm_title(title)
            for bt in self.blacklisted_titles:
                if bt and len(bt) > 10 and (bt in nt or nt in bt):
                    return True
        if self.max_publication_year and pub_year and pub_year >= self.max_publication_year:
            return True
        return False

    def search_valency_works(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search literature via Valency Bond MCP endpoint (PubMed, arXiv, bioRxiv, etc.)
        with strict anti-leakage filtering and high-speed semantic ranking.
        """
        if not self.valency:
            return []

        try:
            raw_papers = self.valency.semantic_search(
                query=query,
                limit=min(max_results * 3, 20),
                include_abstract=True,
            )
        except Exception as e:
            return []

        results: List[Dict] = []
        for item in raw_papers:
            title = item.get("title", "").strip()
            doi = item.get("doi", "").strip() or None

            pub_year = None
            date_val = (
                item.get("dates", {}).get("first_available", {}).get("value")
                or item.get("datestamp")
            )
            if date_val and len(str(date_val)) >= 4 and str(date_val)[:4].isdigit():
                pub_year = int(str(date_val)[:4])
            elif str(item.get("publication_year", "")).isdigit():
                pub_year = int(item["publication_year"])

            if self._is_leaked_or_blocked(title, doi, pub_year):
                continue

            abstract = item.get("abstract", "").strip()
            if not abstract:
                continue

            paper_id = f"VAL_{item.get('source', 'paper')}_{item.get('id', '')}"
            url = item.get("url") or (f"https://doi.org/{doi}" if doi else "")
            record = {
                "paper_id": paper_id,
                "title": title,
                "doi": doi,
                "publication_year": pub_year,
                "cited_by_count": item.get("citation_count", 0),
                "abstract": abstract,
                "url": url,
                "source": f"valency_{item.get('source', 'paper')}",
                "relevance_score": item.get("relevance_score", 0.0),
            }
            results.append(record)
            self.retrieved_sources_log.append(
                {"title": title, "url": url, "year": str(pub_year), "engine": "valency"}
            )
            if len(results) >= max_results:
                break

        return results

    def search_literature(self, query: str, max_results: int = 5) -> List[Dict]:
        """Unified multi-engine literature search prioritizing Valency (sub-second vector search)
        with automated fallback to OpenAlex and EuropePMC.
        """
        results: List[Dict] = []
        if self.valency:
            results.extend(self.search_valency_works(query, max_results=max_results))

        if len(results) < max_results:
            oa_hits = self.search_openalex_works(query, max_results=max_results - len(results))
            results.extend(oa_hits)

        return results[:max_results]

    def search_europepmc_open_access(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search EuropePMC REST API via isolated curl subprocess."""
        q = f"({query})"
        if self.max_publication_year:
            q += f" AND (FIRST_PDATE:[1990-01-01 TO {self.max_publication_year - 1}-12-31])"
        params = {
            "query": q,
            "format": "json",
            "resultType": "core",
            "pageSize": min(max_results * 3, 20),
        }
        results: List[Dict] = []
        data = safe_curl_get_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search", params, max_time_s=8
        )
        if data:
            items = data.get("resultList", {}).get("result", [])
            for item in items:
                title = item.get("title", "")
                doi = item.get("doi")
                pub_year = (
                    int(item["pubYear"]) if str(item.get("pubYear", "")).isdigit() else None
                )
                if self._is_leaked_or_blocked(title, doi, pub_year):
                    continue
                abstract = item.get("abstractText", "")
                if not abstract:
                    continue
                pmcid = item.get("pmcid") or item.get("pmid") or item.get("id")
                url = (
                    f"https://doi.org/{doi}"
                    if doi
                    else f"https://europepmc.org/article/MED/{item.get('pmid', '')}"
                )
                record = {
                    "paper_id": f"EPMC_{pmcid}",
                    "title": title,
                    "doi": doi,
                    "publication_year": pub_year,
                    "cited_by_count": item.get("citedByCount", 0),
                    "abstract": abstract,
                    "url": url,
                }
                results.append(record)
                self.retrieved_sources_log.append(
                    {"title": title, "url": url, "year": str(pub_year)}
                )
                if len(results) >= max_results:
                    break
        return results

    def search_openalex_works(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search OpenAlex works API with user's OPENALEX_API_KEY via isolated curl subprocess + EuropePMC fallback."""
        results: List[Dict] = []
        params: Dict[str, str | int] = {
            "search": query,
            "per-page": min(max_results * 2, 15),
            "sort": "cited_by_count:desc",
        }
        if self.max_publication_year:
            params["filter"] = f"publication_year:<{self.max_publication_year}"
        if self.openalex_api_key:
            params["api_key"] = self.openalex_api_key
        else:
            params["mailto"] = "perturbmat_osi_hackathon@opensource.science"

        data = safe_curl_get_json("https://api.openalex.org/works", params, max_time_s=8)
        if data and isinstance(data.get("results"), list):
            for item in data.get("results", []):
                title = item.get("display_name") or item.get("title") or ""
                doi = item.get("doi")
                pub_year = item.get("publication_year")
                if self._is_leaked_or_blocked(title, doi, pub_year):
                    continue
                abstract = self.reconstruct_abstract(item.get("abstract_inverted_index"))
                if not abstract:
                    continue
                work_url = doi or item.get("id") or ""
                record = {
                    "paper_id": f"OA_{item.get('id', '').split('/')[-1]}",
                    "title": title,
                    "doi": doi,
                    "publication_year": pub_year,
                    "cited_by_count": item.get("cited_by_count", 0),
                    "abstract": abstract,
                    "url": work_url,
                }
                results.append(record)
                self.retrieved_sources_log.append(
                    {"title": title, "url": work_url, "year": str(pub_year)}
                )
                if len(results) >= max_results:
                    break

        if len(results) < max_results:
            epmc_hits = self.search_europepmc_open_access(
                query, max_results=max_results - len(results)
            )
            results.extend(epmc_hits)
        return results[:max_results]

    def snowball_from_seed_extractions(
        self,
        seed_extractions: List[PaperExtraction],
        domain_topic: str = "gold nanobipyramid seed-mediated synthesis mechanism",
        max_new_papers: int = 6,
    ) -> tuple[List[PaperExtraction], List[PDFDocumentChunk]]:
        """Identify foundational/missing papers from the seed papers' cited references and domain topic,
        fetch them via OpenAlex & EuropePMC, and extract structured CMO edges + chunks.
        """
        existing_titles = {self._norm_title(p.title) for p in seed_extractions if p.title}
        candidate_queries: List[str] = [
            domain_topic,
            "gold nanobipyramids pentatwinned seed growth silver underpotential deposition",
        ]

        for p in seed_extractions:
            for ref in p.key_cited_references[:2]:
                if len(ref) > 15:
                    candidate_queries.append(ref)

        raw_records: Dict[str, Dict] = {}
        for q in candidate_queries[:4]:
            for rec in self.search_literature(q, max_results=3):
                nt = self._norm_title(rec["title"])
                if nt not in existing_titles and nt not in raw_records and rec.get("abstract"):
                    raw_records[nt] = rec
            if len(raw_records) >= max_new_papers:
                break

        expanded_extractions: List[PaperExtraction] = []
        expanded_chunks: List[PDFDocumentChunk] = []
        uncached_records: List[Dict] = []

        selected_items = list(raw_records.items())[:max_new_papers]
        for idx, (_, rec) in enumerate(selected_items, 1):
            paper_id = rec["paper_id"]
            cache_path = self.expanded_dir / f"{paper_id}.json"
            text_blob = (
                f"Title: {rec['title']}\n"
                f"Year: {rec.get('publication_year')}\n"
                f"DOI/URL: {rec.get('url')}\n"
                f"Abstract:\n{rec.get('abstract', '')}"
            )
            expanded_chunks.append(
                PDFDocumentChunk(
                    chunk_id=f"{paper_id}_abstract",
                    paper_id=paper_id,
                    text=f"[Expanded Literature: {rec['title']} ({rec.get('publication_year')})]\n{text_blob}",
                    is_si=False,
                    page_num=1,
                )
            )
            if cache_path.exists():
                try:
                    ext = PaperExtraction.model_validate_json(cache_path.read_text())
                    expanded_extractions.append(ext)
                    continue
                except Exception:
                    pass
            uncached_records.append(rec)

        if uncached_records:
            from pydantic import BaseModel as _BM
            from src.models.schemas import CMOPerturbationEdge

            class _SingleSnowballItem(_BM):
                paper_id: str
                core_system_studied: str
                parameters_varied: List[str]
                cmo_edges: List[CMOPerturbationEdge]

            class _BatchSnowballCMO(_BM):
                items: List[_SingleSnowballItem]

            batch_prompt_parts = []
            for r in uncached_records:
                batch_prompt_parts.append(
                    f"--- PAPER_ID: {r['paper_id']} | TITLE: {r['title']} ({r.get('publication_year')}) ---\n"
                    f"Abstract: {r.get('abstract', '')[:1200]}"
                )
            try:
                print(
                    f"    -> [Snowball Batch] Extracting CMO edges from {len(uncached_records)} external papers in 1 batched API call...",
                    flush=True,
                )
                batch_res = self.llm.generate_structured(
                    prompt="Extract Condition-Mechanism-Outcome (CMO) relationships and varied synthesis parameters for each external paper below:\n\n"
                    + "\n\n".join(batch_prompt_parts),
                    schema_cls=_BatchSnowballCMO,
                    system_instruction="Extract structured materials synthesis CMO relationships for each paper_id.",
                )
                by_id = {item.paper_id: item for item in batch_res.items}
                for r in uncached_records:
                    pid = r["paper_id"]
                    matched = by_id.get(pid)
                    ext = PaperExtraction(
                        paper_id=pid,
                        title=r["title"],
                        authors_short="External Snowball Paper",
                        publication_year=r.get("publication_year"),
                        doi=r.get("doi"),
                        core_system_studied=matched.core_system_studied if matched else "Gold nanobipyramid synthesis",
                        parameters_varied=matched.parameters_varied if matched else [],
                        parameters_held_constant=[],
                        synthesis_runs=[],
                        cmo_edges=matched.cmo_edges if matched else [],
                        untested_assumptions_or_limitations=[],
                        key_cited_references=[],
                    )
                    (self.expanded_dir / f"{pid}.json").write_text(ext.model_dump_json(indent=2))
                    expanded_extractions.append(ext)
            except Exception as e:
                print(f"    -> [Snowball batch warning: {e}]", flush=True)

        return expanded_extractions, expanded_chunks
