"""Automated Supplementary Information (SI) Fetcher and Open-Access Resolver.
Extracts DOIs from research PDFs and attempts to automatically discover and download
the corresponding Supplementary Information (.pdf / .docx) from open scientific repositories.
"""

import re
import urllib.request
import urllib.parse
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import pymupdf as fitz


DOI_REGEX = re.compile(
    r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b"
)


class SIFetcher:
    """Discovers and downloads Supplementary Information files for research papers."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or (Path.cwd() / "outputs" / "downloaded_si")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def extract_doi_and_title_from_pdf(
        cls, pdf_path: Path, max_pages: int = 2
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract DOI and estimated title from the first few pages of a PDF."""
        doi: Optional[str] = None
        title: Optional[str] = None

        try:
            doc = fitz.open(str(pdf_path))
            first_pages_text = []
            for i in range(min(max_pages, len(doc))):
                txt = doc[i].get_text("text")
                if txt:
                    first_pages_text.append(txt)
            doc.close()

            combined = "\n".join(first_pages_text)

            # Find DOI
            matches = DOI_REGEX.findall(combined)
            for m in matches:
                clean_m = m.strip().rstrip(".").rstrip(",")
                if len(clean_m) > 10 and not clean_m.endswith("/"):
                    doi = clean_m
                    break

            # Estimate Title: look at lines in first page
            if first_pages_text:
                lines = [l.strip() for l in first_pages_text[0].split("\n") if len(l.strip()) > 15]
                for l in lines[:6]:
                    if not any(
                        k in l.lower()
                        for k in ["doi", "issn", "vol", "issue", "published", "http", "copyright", "rights reserved"]
                    ):
                        title = l
                        break

        except Exception:
            pass

        return doi, title

    def fetch_supplementary_info(
        self, doi: Optional[str], title: Optional[str] = None, paper_stem: str = "paper"
    ) -> Tuple[Optional[Path], str]:
        """Attempt to automatically locate and download the SI file.
        Returns (si_path, status_message).
        """
        if not doi:
            return None, "No DOI detected in the uploaded PDF. Please provide the SI file manually."

        # Check existing cache
        cached_candidates = list(self.cache_dir.glob(f"{paper_stem}_si*"))
        if cached_candidates and cached_candidates[0].stat().st_size > 1000:
            return cached_candidates[0], f"Found existing cached SI: {cached_candidates[0].name}"

        # 1. Try PMC Direct Supplementary endpoint if PMCID is available via EuropePMC search
        try:
            q = urllib.parse.urlencode({"query": f"DOI:{doi}", "format": "json", "resultType": "core"})
            epmc_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{q}"
            req = urllib.request.Request(epmc_url, headers={"User-Agent": "PerturbMat/0.1"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("resultList", {}).get("result", [])
                if results:
                    pmcid = results[0].get("pmcid")
                    if pmcid:
                        supp_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
                        downloaded = self._download_and_validate(supp_url, paper_stem, suffix=".pdf")
                        if downloaded:
                            return downloaded, f"Successfully auto-fetched open-access SI via EuropePMC ({pmcid})!"
        except Exception:
            pass

        # 2. Try Direct Publisher Supplementary patterns (Open-Access journals)
        doi_clean = doi.strip().lower()
        candidate_urls = []
        if "10.1038/" in doi_clean:
            suffix = doi_clean.split("10.1038/")[-1]
            candidate_urls.append(f"https://static-content.springer.com/esm/art%3A10.1038%2F{suffix}/MediaObjects/{suffix}_MOESM1_ESM.pdf")
        elif "10.1039/" in doi_clean:
            rsc_id = doi_clean.split("10.1039/")[-1].upper()
            candidate_urls.append(f"https://www.rsc.org/suppdata/{rsc_id[:2]}/{rsc_id[:4]}/{rsc_id}/{rsc_id}.pdf")
        elif "10.1021/" in doi_clean:
            acs_suffix = doi_clean.split("10.1021/")[-1].replace("/", "_")
            candidate_urls.append(f"https://pubs.acs.org/doi/suppl/{doi}/suppl_file/{acs_suffix}_si_001.pdf")

        for c_url in candidate_urls:
            downloaded = self._download_and_validate(c_url, paper_stem, suffix=".pdf")
            if downloaded:
                return downloaded, f"Successfully auto-downloaded SI from publisher repository ({Path(c_url).name})!"

        return None, (
            f"DOI '{doi}' was detected, but the publisher requires institutional subscription or login. "
            "Please drag and drop the Supplementary Information (.pdf or .docx) manually."
        )

    def _download_and_validate(self, url: str, paper_stem: str, suffix: str = ".pdf") -> Optional[Path]:
        """Download file and verify it is a valid PDF or DOCX rather than an HTML 403 login page."""
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)",
                    "Accept": "application/pdf,application/octet-stream,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                content = resp.read()
                # Check magic bytes for PDF (%PDF-) or DOCX (PK\x03\x04)
                if len(content) > 2000 and (content.startswith(b"%PDF-") or content.startswith(b"PK\x03\x04")):
                    target = self.cache_dir / f"{paper_stem}_si{suffix}"
                    target.write_bytes(content)
                    return target
        except Exception:
            pass
        return None
