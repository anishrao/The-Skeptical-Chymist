"""Verify local PDF and DOCX text extraction across all uploaded seed papers, SIs, and held-out papers."""

from pathlib import Path
from src.ingestion.pdf_extractor import PDFPaperIngestor, SI_PATTERNS


def main():
    root = Path(__file__).resolve().parents[1]
    seed_dir = root / "data" / "seed_papers"
    held_out_dir = root / "data" / "held_out_papers"

    paired = PDFPaperIngestor.pair_main_and_si_pdfs(seed_dir)
    print(f"=== SEED PAPERS & PAIRED SIs ({len(paired)} entries) ===")
    for idx, (main_pdf, si_list) in enumerate(paired, 1):
        m_txt, m_pages = PDFPaperIngestor.extract_text_from_file(main_pdf)
        first_line = next(
            (
                line.strip()
                for line in m_txt.splitlines()
                if len(line.strip()) > 25 and not line.strip().startswith("--- [Page")
            ),
            "",
        )
        si_info = []
        for si in si_list:
            s_txt, s_pages = PDFPaperIngestor.extract_text_from_file(si)
            si_info.append(f"{si.name} ({len(s_txt):,} chars)")
        print(
            f"{idx:2d}. {main_pdf.name} ({len(m_pages)} pages, {len(m_txt):,} chars) "
            f"| SI: {', '.join(si_info) if si_info else 'None'}"
        )
        print(f"    Snippet: {first_line[:100]}")

    print("\n=== HELD-OUT PAPERS & SIs ===")
    for f in sorted(held_out_dir.glob("*")):
        if f.suffix.lower() in {".pdf", ".docx"}:
            txt, pages = PDFPaperIngestor.extract_text_from_file(f)
            role = "Held-Out SI" if (f.suffix.lower() == ".docx" or SI_PATTERNS.search(f.stem)) else "Held-Out Main Paper"
            print(f"- [{role}] {f.name}: {len(pages)} pages/sections, {len(txt):,} chars extracted")


if __name__ == "__main__":
    main()
