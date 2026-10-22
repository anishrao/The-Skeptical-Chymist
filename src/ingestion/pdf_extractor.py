"""PDF + DOCX + Supplementary Information (SI) Extractor and Blinded Held-Out Benchmark Extractor."""

import re
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pymupdf as fitz

from src.llm.gemini_client import GeminiLLMClient
from src.models.schemas import PaperExtraction, BlindedHeldOutBenchmarkCase


SI_PATTERNS = re.compile(
    r"(_si|-si|_supp|-supp|supporting|supplementary|mmc1|moesm|sup-0001)",
    re.IGNORECASE,
)


class PDFDocumentChunk:
    def __init__(
        self,
        chunk_id: str,
        paper_id: str,
        text: str,
        is_si: bool = False,
        page_num: int = 1,
    ):
        self.chunk_id = chunk_id
        self.paper_id = paper_id
        self.text = text
        self.is_si = is_si
        self.page_num = page_num


class PDFPaperIngestor:
    """Ingests seed papers (.pdf) + their Supplementary Information (.pdf / .docx) files,
    and prepares blinded held-out test papers.
    """

    def __init__(self, llm_client: GeminiLLMClient, cache_dir: Optional[Path] = None):
        self.llm = llm_client
        self.cache_dir = cache_dir
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def extract_text_from_docx(docx_path: Path) -> Tuple[str, List[Tuple[int, str]]]:
        """Extract all paragraphs and table cells from a .docx file using built-in zipfile + XML."""
        parts: List[str] = []
        try:
            with zipfile.ZipFile(docx_path) as zf:
                if "word/document.xml" in zf.namelist():
                    xml_bytes = zf.read("word/document.xml")
                    root = ET.fromstring(xml_bytes)
                    # Extract text from paragraphs and table rows
                    for elem in root.iter():
                        if elem.tag.endswith("}p"):
                            texts = [t.text for t in elem.iter() if t.tag.endswith("}t") and t.text]
                            if texts:
                                parts.append("".join(texts))
        except Exception as e:
            parts.append(f"[Error reading docx {docx_path.name}: {e}]")

        full_text = "\n".join(parts)
        # Group into pseudo-pages of ~3000 chars for chunking
        pages: List[Tuple[int, str]] = []
        step = 3000
        for i in range(0, max(1, len(full_text)), step):
            pages.append((i // step + 1, full_text[i : i + step]))
        return full_text, pages

    @classmethod
    def extract_text_from_file(cls, file_path: Path, max_pages: int = 60) -> Tuple[str, List[Tuple[int, str]]]:
        """Extract text and page tuples from either a .pdf or .docx file."""
        if file_path.suffix.lower() == ".docx":
            return cls.extract_text_from_docx(file_path)
        doc = fitz.open(str(file_path))
        pages: List[Tuple[int, str]] = []
        full_parts: List[str] = []
        for idx, page in enumerate(doc):
            if idx >= max_pages:
                break
            txt = page.get_text("text")
            if txt and txt.strip():
                pages.append((idx + 1, txt))
                full_parts.append(f"\n--- [Page {idx + 1}] ---\n{txt}")
        doc.close()
        return "\n".join(full_parts), pages

    @staticmethod
    def pair_main_and_si_pdfs(seed_dir: Path) -> List[Tuple[Path, List[Path]]]:
        """Automatically pair main research paper PDFs in `seed_dir` with their Supplementary Information
        (.pdf and .docx) located in `seed_dir/supplementary_info/` or inside `seed_dir`.
        """
        all_top_files = sorted(
            [p for p in seed_dir.glob("*") if p.suffix.lower() in {".pdf", ".docx"}]
        )
        si_subdir = seed_dir / "supplementary_info"
        si_files: List[Path] = []
        if si_subdir.exists():
            si_files.extend(
                sorted([p for p in si_subdir.glob("*") if p.suffix.lower() in {".pdf", ".docx"}])
            )

        main_pdfs: List[Path] = []
        for f in all_top_files:
            if SI_PATTERNS.search(f.stem) or f.suffix.lower() == ".docx":
                si_files.append(f)
            else:
                main_pdfs.append(f)

        paired: Dict[Path, List[Path]] = {m: [] for m in main_pdfs}
        unmatched_sis: List[Path] = []

        for si in si_files:
            si_low = si.stem.lower()
            clean_si = SI_PATTERNS.sub("", si_low).strip("_- ")
            best_main: Optional[Path] = None
            best_score = 0

            for m in main_pdfs:
                m_low = m.stem.lower().replace("-main", "")
                score = 0
                # Direct substring check (e.g., 'ncomms8571' in '41467_2015_bfncomms8571_moesm97_esm',
                # 's0022369720315158' in '1-s2.0-s0022369720315158-mmc1', 'c4nr06323f' in 'c4nr06323f1_suppl')
                if m_low in si_low or clean_si in m_low:
                    score += 100
                # Journal abbreviation mapping (e.g. 'adom' <-> 'advanced optical materials')
                if "adom" in si_low and "advanced optical materials" in m_low:
                    score += 90
                if "smll" in si_low and "small" in m_low:
                    score += 90
                # Prefix match
                common_prefix = 0
                for a, b in zip(m_low, clean_si):
                    if a == b:
                        common_prefix += 1
                    else:
                        break
                if common_prefix >= 6:
                    score += common_prefix * 5

                if score > best_score:
                    best_score = score
                    best_main = m

            if best_main is not None and best_score >= 30:
                paired[best_main].append(si)
            else:
                unmatched_sis.append(si)

        result = [(m, paired[m]) for m in main_pdfs]
        # Also include any standalone SI PDF whose main paper wasn't uploaded separately
        for standalone_si in unmatched_sis:
            if standalone_si.suffix.lower() == ".pdf":
                result.append((standalone_si, []))
        return result

    def chunk_paper_and_si(
        self,
        paper_id: str,
        main_pages: List[Tuple[int, str]],
        si_pages_list: List[List[Tuple[int, str]]],
        chunk_chars: int = 1800,
        overlap_chars: int = 300,
    ) -> List[PDFDocumentChunk]:
        """Create overlapping text chunks preserving page numbers and Main vs. SI provenance."""
        chunks: List[PDFDocumentChunk] = []
        c_idx = 0

        def _chunk_pages(pages: List[Tuple[int, str]], is_si: bool):
            nonlocal c_idx
            for page_num, page_text in pages:
                text = page_text.strip()
                start = 0
                while start < len(text):
                    end = min(len(text), start + chunk_chars)
                    snippet = text[start:end]
                    tag = "SI" if is_si else "Main"
                    c_idx += 1
                    chunks.append(
                        PDFDocumentChunk(
                            chunk_id=f"{paper_id}_{tag}_p{page_num}_c{c_idx}",
                            paper_id=paper_id,
                            text=f"[Source: {paper_id} ({tag}, Page {page_num})]\n{snippet}",
                            is_si=is_si,
                            page_num=page_num,
                        )
                    )
                    if end >= len(text):
                        break
                    start = end - overlap_chars

        _chunk_pages(main_pages, is_si=False)
        for si_pages in si_pages_list:
            _chunk_pages(si_pages, is_si=True)
        return chunks

    def extract_structured_paper(
        self, main_pdf: Path, si_files: List[Path], force_reextract: bool = False
    ) -> Tuple[PaperExtraction, List[PDFDocumentChunk]]:
        """Extract Condition-Mechanism-Outcome (CMO) causal edges, synthesis recipe tables, and chunks from a paper + its SIs."""
        paper_id = main_pdf.stem
        cache_file = self.cache_dir / f"{paper_id}_extraction.json" if self.cache_dir else None
        chunks_cache_file = self.cache_dir / f"{paper_id}_chunks.json" if self.cache_dir else None

        if (
            cache_file
            and cache_file.exists()
            and chunks_cache_file
            and chunks_cache_file.exists()
            and not force_reextract
        ):
            extraction = PaperExtraction.model_validate_json(cache_file.read_text())
            raw_chunks = json.loads(chunks_cache_file.read_text())
            chunks = [PDFDocumentChunk(**c) for c in raw_chunks]
            return extraction, chunks

        main_text, main_pages = self.extract_text_from_file(main_pdf)
        si_texts: List[str] = []
        si_pages_list: List[List[Tuple[int, str]]] = []
        for si_f in si_files:
            s_txt, s_pages = self.extract_text_from_file(si_f, max_pages=45)
            si_texts.append(f"\n=== SUPPLEMENTARY INFORMATION ({si_f.name}) ===\n{s_txt}")
            si_pages_list.append(s_pages)

        chunks = self.chunk_paper_and_si(paper_id, main_pages, si_pages_list)
        if chunks_cache_file:
            chunks_cache_file.write_text(json.dumps([vars(c) for c in chunks]))

        combined_text = main_text[:65000]
        if si_texts:
            combined_text += "\n\n" + "\n".join(si_texts)[:35000]

        if cache_file and cache_file.exists() and not force_reextract:
            extraction = PaperExtraction.model_validate_json(cache_file.read_text())
            return extraction, chunks

        system_instruction = (
            "You are an expert materials chemistry & nanomaterial synthesis extractor. "
            "Extract precise experimental recipes and at least 3-6 directional Condition-Mechanism-Outcome (CMO) perturbation relationships "
            "(ΔX -> Physical Mechanism -> ΔY with fixed boundary conditions) from the research paper and its Supplementary Information. "
            "Pay special attention to nanoparticle morphology metrics: particle volume, tip-to-tip length, equatorial width, "
            "aspect ratio, longitudinal LSPR wavelength, pentatwinned seed quality, and shape yield."
        )
        prompt = (
            f"Paper ID: {paper_id}\n"
            f"Attached SI files: {[p.name for p in si_files]}\n\n"
            "Extract the structured PaperExtraction object from the following paper and SI text:\n\n"
            f"{combined_text}"
        )

        extraction = self.llm.generate_structured(
            prompt=prompt,
            schema_cls=PaperExtraction,
            system_instruction=system_instruction,
        )
        extraction.paper_id = paper_id

        if cache_file:
            cache_file.write_text(extraction.model_dump_json(indent=2))

        return extraction, chunks

    def extract_held_out_benchmark_case(
        self, held_out_pdf: Path, held_out_si_files: Optional[List[Path]] = None
    ) -> BlindedHeldOutBenchmarkCase:
        """Parse a held-out test paper from `data/held_out_papers/` into:
        1. A strictly BLINDED baseline protocol + perturbation question (safe to pass to the agent).
        2. The hidden Ground-Truth outcome & mechanism (used only by the evaluator after prediction).
        """
        paper_id = held_out_pdf.stem
        main_text, _ = self.extract_text_from_file(held_out_pdf)
        si_part = ""
        if held_out_si_files:
            for si in held_out_si_files:
                s_txt, _ = self.extract_text_from_file(si, max_pages=30)
                si_part += f"\n=== HELD-OUT SI ({si.name}) ===\n{s_txt[:25000]}"

        system_instruction = (
            "You are designing a strict, leak-free scientific benchmark from a held-out experimental materials science paper. "
            "You must separate the paper into:\n"
            "1. `blinded_baseline_protocol` and `perturbation_question`: Contains ONLY the starting synthesis conditions and "
            "the experimental perturbation X that the authors tested. CRITICAL: Do NOT leak any experimental results, "
            "observed directions of change, mechanisms, or paper title/authors inside `blinded_baseline_protocol` or `perturbation_question`!\n"
            "2. `ground_truth_summary`, `ground_truth_observables`, and `ground_truth_mechanism_explained_by_authors`: "
            "The actual experimental findings (e.g., whether gold bipyramid volume, aspect ratio, length, width, LSPR peak, and yield "
            "increased, decreased, or showed non-monotonic behavior, with exact numbers and the authors' physical explanation)."
        )
        prompt = (
            f"Held-out Paper Filename: {paper_id}\n\n"
            "Extract the BlindedHeldOutBenchmarkCase from the text below:\n\n"
            f"{main_text[:70000]}\n{si_part}"
        )

        case = self.llm.generate_structured(
            prompt=prompt,
            schema_cls=BlindedHeldOutBenchmarkCase,
            system_instruction=system_instruction,
        )
        case.held_out_paper_id = paper_id
        return case
