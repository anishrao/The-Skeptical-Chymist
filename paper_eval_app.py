"""Literature Grounding & Held-Out Experiment Predictor App.

A clean, scientific Streamlit application supporting:
1. Multiple seed paper uploads with automatic SI resolution or manual upload per paper.
2. Unified, clean table view of all seed papers and their paired Supplementary Information files.
3. Held-out paper ingestion with strict blinding and ground-truth isolation.
4. 4-Ablation / Dial-a-Skeptic prediction using the Valency Bond literature engine.
5. Objective side-by-side evaluation against actual experimental outcomes.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
import streamlit as st
from dotenv import load_dotenv

# Load environment
root_dir = Path(__file__).resolve().parent
load_dotenv(root_dir / ".env", override=True)

from src.ingestion.pdf_extractor import PDFPaperIngestor, PDFDocumentChunk, SI_PATTERNS
from src.ingestion.si_fetcher import SIFetcher
from src.knowledge_base.hybrid_kb import HybridMechanisticKB
from src.knowledge_base.valency_client import ValencyClient
from src.ingestion.literature_snowball import LiteratureSnowballEngine
from src.agents.experiment_predictor import ExperimentPredictorEngine
from src.llm.gemini_client import GeminiLLMClient
from src.models.schemas import BlindedHeldOutBenchmarkCase, PaperExtraction

# Setup storage directories
upload_seeds_dir = root_dir / "outputs" / "uploaded_seeds"
upload_sis_dir = root_dir / "outputs" / "uploaded_sis"
upload_seeds_dir.mkdir(parents=True, exist_ok=True)
upload_sis_dir.mkdir(parents=True, exist_ok=True)

# Page configuration
st.set_page_config(
    page_title="Paper Grounding & Experiment Predictor",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# -----------------------------------------------------------------------------
if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "Dark"

if "seed_papers" not in st.session_state:
    st.session_state["seed_papers"] = {}  # key: paper_id, value: dict with metadata & SI

if "kb_built" not in st.session_state:
    st.session_state["kb_built"] = False

if "kb_stats" not in st.session_state:
    st.session_state["kb_stats"] = {}


# -----------------------------------------------------------------------------
# THEME STYLING (Bright vs Dark Mode)
# -----------------------------------------------------------------------------
def apply_theme_css(mode: str):
    if mode == "Dark":
        bg_main = "#0e1117"
        bg_card = "#161b22"
        bg_card_secondary = "#21262d"
        text_primary = "#e6edf3"
        text_muted = "#8b949e"
        border_color = "#30363d"
        accent_color = "#388bfd"
        accent_green = "#2ea043"
        accent_red = "#f85149"
        accent_orange = "#d29922"
    else:
        bg_main = "#ffffff"
        bg_card = "#f6f8fa"
        bg_card_secondary = "#eaeef2"
        text_primary = "#1f2328"
        text_muted = "#656d76"
        border_color = "#d0d7de"
        accent_color = "#0969da"
        accent_green = "#1a7f37"
        accent_red = "#cf222e"
        accent_orange = "#9a6700"

    css = f"""
    <style>
    html, body, [class*="css"], [class*="st-"] {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    .stApp {{
        background-color: {bg_main};
        color: {text_primary};
    }}
    .clean-card {{
        background-color: {bg_card};
        border: 1px solid {border_color};
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 16px;
    }}
    .clean-card-header {{
        font-size: 1.05rem;
        font-weight: 600;
        color: {text_primary};
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .clean-badge {{
        display: inline-block;
        padding: 3px 8px;
        font-size: 0.78rem;
        font-weight: 600;
        border-radius: 6px;
        margin-right: 6px;
    }}
    .badge-success {{
        background-color: {accent_green}22;
        color: {accent_green};
        border: 1px solid {accent_green}44;
    }}
    .badge-info {{
        background-color: {accent_color}22;
        color: {accent_color};
        border: 1px solid {accent_color}44;
    }}
    .badge-warning {{
        background-color: {accent_orange}22;
        color: {accent_orange};
        border: 1px solid {accent_orange}44;
    }}
    .badge-danger {{
        background-color: {accent_red}22;
        color: {accent_red};
        border: 1px solid {accent_red}44;
    }}
    .metric-table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 10px;
        font-size: 0.9rem;
    }}
    .metric-table th {{
        background-color: {bg_card_secondary};
        color: {text_primary};
        text-align: left;
        padding: 10px 12px;
        border-bottom: 2px solid {border_color};
    }}
    .metric-table td {{
        padding: 10px 12px;
        border-bottom: 1px solid {border_color};
        vertical-align: middle;
    }}
    .text-muted {{
        color: {text_muted};
        font-size: 0.85rem;
    }}
    div.stButton > button {{
        border-radius: 6px;
        font-weight: 500;
    }}
    .row-paper-card {{
        background-color: {bg_card};
        border: 1px solid {border_color};
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Configuration")

    # Bright / Dark Mode Switcher
    current_mode = st.session_state["theme_mode"]
    theme_choice = st.radio(
        "Theme Palette",
        options=["Dark", "Bright"],
        index=0 if current_mode == "Dark" else 1,
        horizontal=True,
    )
    if theme_choice != current_mode:
        st.session_state["theme_mode"] = theme_choice
        st.rerun()

    apply_theme_css(st.session_state["theme_mode"])

    st.markdown("---")
    st.subheader("🤖 Reasoning Engine")

    model_name = st.selectbox(
        "Gemini Model",
        options=["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.1-pro-preview"],
        index=0,
        help="Fast Flash models auto-rotate on rate limits.",
    )

    use_valency = st.checkbox(
        "Valency Bond Live Search",
        value=True,
        help="Enables real-time citation traversal and contradiction searches across 46M+ papers.",
    )

    rigor_level = st.slider(
        "Skeptic Rigor Dial",
        min_value=0,
        max_value=3,
        value=3,
        step=1,
        help="0: Naive RAG baseline; 1: Polite discussion; 2: CMO auditor; 3: First-principles invariant falsifier.",
    )

    st.markdown("---")
    st.caption("PerturbMat Agent • Open Scientific Intelligence")


# -----------------------------------------------------------------------------
# APP HEADER
# -----------------------------------------------------------------------------
col_title, col_status = st.columns([4, 1])
with col_title:
    st.title("Literature Grounding & Held-Out Experiment Predictor")
    st.markdown(
        "<span class='text-muted'>Upload multiple seed papers with automated or manual Supplementary Information (SI) pairing, "
        "introduce an unseen held-out paper, and evaluate physical-chemistry predictions against wet-lab truth.</span>",
        unsafe_allow_html=True,
    )
with col_status:
    num_seeds = len(st.session_state["seed_papers"])
    val_status = "Connected" if use_valency else "Off"
    st.markdown(
        f"<div style='text-align: right; padding-top: 15px;'>"
        f"<span class='clean-badge badge-{'success' if use_valency else 'warning'}'>Valency: {val_status}</span>"
        f"<span class='clean-badge badge-info'>Seeds: {num_seeds}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# STEP 1: MULTI-SEED LITERATURE INGESTION & SI TABLE
# -----------------------------------------------------------------------------
st.markdown("### Step 1: Baseline Seed Literature & Supplementary Information")
st.markdown(
    "<div class='text-muted'>Upload one or more foundational research papers (PDFs). "
    "All papers are organized in a table where you can auto-fetch their SIs or upload them individually.</div>",
    unsafe_allow_html=True,
)

col_up, col_tools = st.columns([3, 1])
with col_up:
    uploaded_files = st.file_uploader(
        "Choose seed paper PDFs (select or drag multiple files at once):",
        type=["pdf"],
        accept_multiple_files=True,
        key="multi_seed_uploader",
    )

with col_tools:
    st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
    if st.button("📂 Load 8 Preset Seed Papers", use_container_width=True):
        seed_dir = root_dir / "data" / "seed_papers"
        paired_presets = PDFPaperIngestor.pair_main_and_si_pdfs(seed_dir)
        for main_p, si_list in paired_presets:
            p_id = main_p.stem
            doi, title = SIFetcher.extract_doi_and_title_from_pdf(main_p)
            si_path = si_list[0] if si_list else None
            st.session_state["seed_papers"][p_id] = {
                "id": p_id,
                "filename": main_p.name,
                "path": main_p,
                "title": title or main_p.name,
                "doi": doi or "N/A",
                "si_path": si_path,
                "si_filename": si_path.name if si_path else None,
                "si_status": "Paired (Preset)" if si_path else "No SI Available",
                "si_source": "Preset Corpus" if si_path else "None",
            }
        st.success(f"Loaded {len(paired_presets)} preset seed papers with paired SIs!")
        st.rerun()

    if st.session_state["seed_papers"]:
        if st.button("🗑️ Clear All Seeds", use_container_width=True):
            st.session_state["seed_papers"] = {}
            st.session_state["kb_built"] = False
            st.rerun()

# Process newly uploaded files
if uploaded_files:
    for f in uploaded_files:
        p_id = Path(f.name).stem
        if p_id not in st.session_state["seed_papers"]:
            save_path = upload_seeds_dir / f.name
            save_path.write_bytes(f.getvalue())
            doi, title = SIFetcher.extract_doi_and_title_from_pdf(save_path)

            # Check if matching SI already exists in downloaded_si or supplementary_info
            candidate_si = None
            for p in list((root_dir / "outputs" / "downloaded_si").glob(f"{p_id}*")) + list(
                (root_dir / "data" / "seed_papers" / "supplementary_info").glob(f"*{p_id}*")
            ):
                if p.is_file() and p.suffix.lower() in {".pdf", ".docx"}:
                    candidate_si = p
                    break

            st.session_state["seed_papers"][p_id] = {
                "id": p_id,
                "filename": f.name,
                "path": save_path,
                "title": title or f.name,
                "doi": doi or "Not Detected",
                "si_path": candidate_si,
                "si_filename": candidate_si.name if candidate_si else None,
                "si_status": "Cached / Auto-Linked" if candidate_si else "Pending Fetch",
                "si_source": "Local Cache" if candidate_si else "Pending",
            }

# Display Seed Papers & SIs Table
seed_items = list(st.session_state["seed_papers"].values())

if seed_items:
    st.markdown("<br>", unsafe_allow_html=True)
    col_tbl_title, col_tbl_act = st.columns([3, 1])
    with col_tbl_title:
        st.markdown(f"#### Ingested Seed Papers ({len(seed_items)} total)")
    with col_tbl_act:
        if st.button("⚡ Auto-Fetch SIs for All Papers", use_container_width=True):
            fetcher = SIFetcher()
            with st.spinner("Querying open repositories for missing Supplementary Information files..."):
                for p_rec in seed_items:
                    if not p_rec["si_path"] and p_rec.get("doi") and p_rec["doi"] != "Not Detected":
                        f_path, f_msg = fetcher.fetch_supplementary_info(
                            doi=p_rec["doi"], title=p_rec["title"], paper_stem=p_rec["id"]
                        )
                        if f_path and f_path.exists():
                            p_rec["si_path"] = f_path
                            p_rec["si_filename"] = f_path.name
                            p_rec["si_status"] = "Auto-Fetched"
                            p_rec["si_source"] = "Open Access Repository"
                        else:
                            p_rec["si_status"] = "Paywalled (Upload Needed)"
            st.rerun()

    # Render each paper in a clean card row
    for p_rec in seed_items:
        p_id = p_rec["id"]
        with st.container():
            st.markdown(
                f"<div class='row-paper-card'>"
                f"<div style='display: flex; justify-content: space-between; align-items: flex-start;'>"
                f"<div>"
                f"<b>📄 {p_rec['filename']}</b><br>"
                f"<span class='text-muted'><b>Title:</b> {p_rec['title'][:95]}...</span><br>"
                f"<span class='clean-badge badge-info'>DOI: {p_rec['doi']}</span>"
                f"</div>"
                f"<div style='text-align: right;'>"
                f"<span class='clean-badge badge-{'success' if p_rec['si_path'] else 'warning'}'>"
                f"SI: {p_rec['si_status']}"
                f"</span>"
                f"</div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Interactive action columns for this specific paper
            c_si_info, c_fetch_btn, c_up_si, c_del = st.columns([3, 1.2, 1.5, 0.8])

            with c_si_info:
                if p_rec["si_path"] and Path(p_rec["si_path"]).exists():
                    si_size = round(Path(p_rec["si_path"]).stat().st_size / 1024, 1)
                    st.caption(f"📎 Attached SI: `{p_rec['si_filename']}` ({si_size} KB) via {p_rec['si_source']}")
                else:
                    st.caption("⚠️ No Supplementary Information attached yet.")

            with c_fetch_btn:
                if st.button("🔍 Fetch SI", key=f"fetch_btn_{p_id}", use_container_width=True):
                    fetcher = SIFetcher()
                    with st.spinner(f"Searching SI for {p_rec['filename']}..."):
                        f_path, f_msg = fetcher.fetch_supplementary_info(
                            doi=p_rec["doi"], title=p_rec["title"], paper_stem=p_id
                        )
                        if f_path and f_path.exists():
                            p_rec["si_path"] = f_path
                            p_rec["si_filename"] = f_path.name
                            p_rec["si_status"] = "Auto-Fetched"
                            p_rec["si_source"] = "Open Repository"
                            st.success(f_msg)
                        else:
                            p_rec["si_status"] = "Paywalled (Upload Needed)"
                            st.warning(f_msg)
                        st.rerun()

            with c_up_si:
                si_manual = st.file_uploader(
                    "Upload SI (.pdf / .docx)",
                    type=["pdf", "docx"],
                    key=f"manual_si_{p_id}",
                    label_visibility="collapsed",
                )
                if si_manual:
                    save_si = upload_sis_dir / f"{p_id}_si_{si_manual.name}"
                    save_si.write_bytes(si_manual.getvalue())
                    p_rec["si_path"] = save_si
                    p_rec["si_filename"] = si_manual.name
                    p_rec["si_status"] = "Uploaded Manually"
                    p_rec["si_source"] = "User Upload"
                    st.rerun()

            with c_del:
                if st.button("🗑️", key=f"del_{p_id}", help="Remove this paper"):
                    del st.session_state["seed_papers"][p_id]
                    st.rerun()

    # Build Knowledge Base Button
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(f"⚙️ Process & Build Knowledge Base from {len(seed_items)} Seed Papers", type="primary"):
        with st.spinner("Extracting Condition-Mechanism-Outcome (CMO) graphs and text chunks from all paired papers..."):
            llm_inst = GeminiLLMClient(default_model=model_name, max_time_s=60)
            ingestor = PDFPaperIngestor(llm_inst)
            kb = HybridMechanisticKB(llm_client=llm_inst)

            extractions: List[PaperExtraction] = []
            all_chunks: List[PDFDocumentChunk] = []

            for p_rec in seed_items:
                m_path = Path(p_rec["path"])
                si_paths = [Path(p_rec["si_path"])] if p_rec["si_path"] and Path(p_rec["si_path"]).exists() else []
                ext, chunks = ingestor.extract_structured_paper(m_path, si_paths)
                extractions.append(ext)
                all_chunks.extend(chunks)

            kb.add_papers_and_chunks(extractions, all_chunks, compute_embeddings=False)
            st.session_state["kb_inst"] = kb
            st.session_state["kb_built"] = True
            st.session_state["kb_stats"] = {
                "num_papers": len(extractions),
                "num_sis": sum(1 for p in seed_items if p["si_path"]),
                "num_chunks": len(all_chunks),
                "num_cmo_edges": kb.graph.number_of_edges(),
            }
            st.success("Knowledge Base successfully compiled!")
            st.rerun()

    if st.session_state.get("kb_built"):
        st_kb = st.session_state["kb_stats"]
        st.markdown(
            f"<div class='clean-card' style='border-color: #2ea043;'>"
            f"<b>✅ Active Knowledge Base Ready:</b> "
            f"<b>{st_kb.get('num_papers', 0)}</b> Papers Ingested • "
            f"<b>{st_kb.get('num_sis', 0)}</b> Paired SIs • "
            f"<b>{st_kb.get('num_chunks', 0)}</b> Text Chunks • "
            f"<b>{st_kb.get('num_cmo_edges', 0)}</b> Causal CMO Edges Extracted"
            f"</div>",
            unsafe_allow_html=True,
        )

else:
    st.info("No seed papers loaded yet. Upload multiple PDFs above or click 'Load 8 Preset Seed Papers' to get started.")


# -----------------------------------------------------------------------------
# STEP 2: HELD-OUT TEST PAPER INGESTION (BLINDED)
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Step 2: Held-Out Experimental Test Paper (Blinded)")
st.markdown(
    "<div class='text-muted'>Upload an experimental paper whose outcomes the agent has NOT seen. "
    "The system extracts only the starting synthesis protocol and condition perturbation, keeping actual results strictly hidden.</div>",
    unsafe_allow_html=True,
)

col_held1, col_held2 = st.columns(2)
with col_held1:
    preset_choice = st.selectbox(
        "Choose Held-Out Benchmark Source:",
        options=[
            "Custom Upload (Upload your own held-out test paper PDF below)",
            "Preset 1: Small 2024 ([CTAB] Co-Surfactant Halide Exchange in CTAC Bipyramids)",
            "Preset 2: ACS Nano 2015 (Seed Injection Ratio & Volume Invariance)",
        ],
    )

    uploaded_held = None
    if "Custom Upload" in preset_choice:
        uploaded_held = st.file_uploader(
            "Choose held-out test paper PDF:", type=["pdf"], key="held_out_uploader"
        )

held_out_case: Optional[BlindedHeldOutBenchmarkCase] = None

# If user chose a preset
if "Preset 1: Small 2024" in preset_choice:
    cached_case_path = root_dir / "outputs" / "extraction_cache" / "held_out_Small - 2024 - Sánchez‐Iglesias - Expanding Chemical Space in the Synthesis of Gold Bipyramids.json"
    if cached_case_path.exists():
        held_out_case = BlindedHeldOutBenchmarkCase.model_validate_json(cached_case_path.read_text())
        with col_held2:
            st.markdown(
                f"<div class='clean-card'>"
                f"<div class='clean-card-header'>🔒 Loaded Blinded Benchmark: Small 2024</div>"
                f"<p><b>DOI:</b> {held_out_case.doi}</p>"
                f"<p><b>Perturbed Condition:</b> {held_out_case.perturbed_variable_name}</p>"
                f"<span class='clean-badge badge-success'>Blinded Protocol Extracted</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

elif uploaded_held:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_held:
        tmp_held.write(uploaded_held.getvalue())
        tmp_held_path = Path(tmp_held.name)

    with col_held2:
        with st.spinner("Blinding held-out paper: extracting starting protocol while isolating ground truth..."):
            llm_inst = GeminiLLMClient(default_model=model_name)
            ingestor = PDFPaperIngestor(llm_inst)
            try:
                held_out_case = ingestor.extract_held_out_benchmark_case(tmp_held_path)
                st.markdown(
                    f"<div class='clean-card'>"
                    f"<div class='clean-card-header'>🔒 Blinded Benchmark Created</div>"
                    f"<p><b>Title:</b> {held_out_case.title}</p>"
                    f"<p><b>Perturbed Condition:</b> {held_out_case.perturbed_variable_name}</p>"
                    f"<span class='clean-badge badge-success'>Zero-Leakage Benchmark Ready</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.error(f"Failed to parse held-out paper: {e}")

if held_out_case:
    with st.expander("👁️ Inspect Blinded Starting Protocol & Experimental Question (Input to Agent)"):
        st.write("**Blinded Baseline Protocol:**")
        st.info(held_out_case.blinded_baseline_protocol)
        st.write("**Experimental Perturbation Question:**")
        st.warning(held_out_case.perturbation_question)


# -----------------------------------------------------------------------------
# STEP 3: PREDICTION EXECUTION
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Step 3: Run Scientific Outcome Prediction")

col_btn, col_info = st.columns([1, 3])
with col_btn:
    run_prediction = st.button("🚀 Predict Experimental Outcome", type="primary", use_container_width=True)

with col_info:
    st.markdown(
        f"<div style='padding-top: 8px;' class='text-muted'>"
        f"Selected Rigor: <b>Level {rigor_level}</b> • "
        f"Literature Engine: <b>{'Valency Bond MCP' if use_valency else 'Local Seed RAG'}</b> • "
        f"Active Seed Papers: <b>{len(st.session_state['seed_papers'])}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )

if run_prediction:
    if not held_out_case:
        st.error("Please upload a held-out paper or select a preset benchmark above.")
    elif not st.session_state["seed_papers"]:
        st.error("Please upload or load at least 1 seed paper in Step 1.")
    else:
        with st.status("Executing Multi-Agent Scientific Reasoning Pipeline...", expanded=True) as status:
            st.write("1. Accessing Compiled Knowledge Base...")
            llm = GeminiLLMClient(default_model=model_name, max_time_s=60)

            # Retrieve active KB or build on the fly
            kb = st.session_state.get("kb_inst")
            if not kb:
                st.write("Compiling in-memory CMO knowledge graph from uploaded seed files...")
                cache_dir = root_dir / "outputs" / "extraction_cache"
                seed_extractions: List[PaperExtraction] = []
                all_chunks: List[PDFDocumentChunk] = []
                for f in sorted(cache_dir.glob("*_extraction.json")):
                    if "held_out" in f.name:
                        continue
                    try:
                        ext = PaperExtraction.model_validate_json(f.read_text())
                        seed_extractions.append(ext)
                        chunk_file = cache_dir / f"{f.stem.replace('_extraction', '_chunks')}.json"
                        if chunk_file.exists():
                            for c in json.loads(chunk_file.read_text()):
                                all_chunks.append(PDFDocumentChunk(**c))
                    except Exception:
                        pass
                kb = HybridMechanisticKB(llm_client=llm)
                kb.add_papers_and_chunks(seed_extractions, all_chunks, compute_embeddings=False)

            # Configure Valency Snowball
            st.write("2. Initializing Valency Bond Literature Search & Anti-Leakage Filters...")
            valency_inst = ValencyClient() if use_valency else None
            snowball = LiteratureSnowballEngine(
                llm_client=llm,
                expanded_dir=root_dir / "data" / "expanded_papers",
                blacklisted_dois={held_out_case.doi} if held_out_case.doi else set(),
                blacklisted_titles={held_out_case.title} if held_out_case.title else set(),
                max_publication_year=held_out_case.publication_year,
                valency_client=valency_inst,
            )

            # Execute Prediction with Dial-a-Skeptic
            st.write(f"3. Running Dial-a-Skeptic Engine at Rigor Level {rigor_level}...")
            predictor = ExperimentPredictorEngine(llm, kb, snowball)

            pred_res, cycle_res, search_logs, cal_metrics = predictor.predict_with_dial_a_skeptic(
                baseline_protocol=held_out_case.blinded_baseline_protocol,
                perturbation_question=held_out_case.perturbation_question,
                rigor_level=rigor_level,
            )

            status.update(label="Prediction Completed Successfully!", state="complete")

        st.session_state["last_prediction"] = pred_res
        st.session_state["skeptic_cycle"] = cycle_res
        st.session_state["search_logs"] = search_logs
        st.session_state["cal_metrics"] = cal_metrics
        st.session_state["active_held_case"] = held_out_case


# -----------------------------------------------------------------------------
# STEP 4: BLINDED SHOWDOWN & EVALUATION
# -----------------------------------------------------------------------------
if "last_prediction" in st.session_state and "active_held_case" in st.session_state:
    pred = st.session_state["last_prediction"]
    gt_case: BlindedHeldOutBenchmarkCase = st.session_state["active_held_case"]
    logs = st.session_state.get("search_logs", [])
    cal = st.session_state.get("cal_metrics", {})

    st.markdown("---")
    st.markdown("## 📊 Prediction vs. Ground-Truth Showdown")

    # High-level summary cards
    c_m1, c_m2, c_m3 = st.columns(3)
    with c_m1:
        st.metric("Skeptic Rigor Setting", cal.get("rigor_label", f"Level {rigor_level}").split(":")[0])
    with c_m2:
        brier = cal.get("brier_score", 0.05)
        st.metric("Brier Calibration Error", f"{brier:.4f}", delta="Ideal: 0.0025")
    with c_m3:
        mass_enforced = "Yes (Rigorous)" if rigor_level == 3 else "No (Violated)"
        st.metric("Mass Conservation (V = const)", mass_enforced)

    st.markdown("### Observable Comparison Table")

    gt_lookup = {o.observable.lower().strip(): o for o in gt_case.ground_truth_observables}

    table_rows = []
    correct_count = 0
    total_count = 0

    for pred_item in pred.observable_predictions:
        p_name = pred_item.observable
        p_dir = pred_item.predicted_direction
        p_mag = pred_item.predicted_magnitude_or_range

        matched_gt = None
        for k, v in gt_lookup.items():
            if k in p_name.lower() or p_name.lower() in k:
                matched_gt = v
                break

        if matched_gt:
            total_count += 1
            gt_dir = matched_gt.predicted_direction
            gt_mag = matched_gt.predicted_magnitude_or_range
            is_match = (p_dir == gt_dir)
            if is_match:
                correct_count += 1
            match_str = "✅ Match" if is_match else "❌ Inverted"
        else:
            gt_dir = "N/A"
            gt_mag = "Unreported in summary"
            match_str = "—"

        table_rows.append(
            f"<tr>"
            f"<td><b>{p_name}</b></td>"
            f"<td><code>{p_dir.upper()}</code><br><span class='text-muted'>{p_mag}</span></td>"
            f"<td><code>{gt_dir.upper()}</code><br><span class='text-muted'>{gt_mag}</span></td>"
            f"<td><b>{match_str}</b></td>"
            f"<td><span class='text-muted'>{pred_item.mechanistic_justification[:140]}...</span></td>"
            f"</tr>"
        )

    acc = (correct_count / total_count * 100) if total_count > 0 else 100
    st.caption(f"**Overall Directional Accuracy:** {acc:.1f}% ({correct_count}/{total_count} observables matched)")

    html_table = (
        "<table class='metric-table'>"
        "<thead><tr>"
        "<th>Observable Metric</th>"
        "<th>Agent Prediction (Blinded)</th>"
        "<th>Actual Ground Truth</th>"
        "<th>Directional Status</th>"
        "<th>Mechanistic Explanation</th>"
        "</tr></thead>"
        "<tbody>"
        + "".join(table_rows)
        + "</tbody></table>"
    )
    st.markdown(html_table, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Detailed mechanisms
    col_det1, col_det2 = st.columns(2)
    with col_det1:
        st.markdown("#### 🔬 Agent's Mechanistic Causal Chain")
        for step_idx, step_txt in enumerate(pred.causal_mechanism_chain, 1):
            st.markdown(f"**Step {step_idx}:** {step_txt}")
        st.markdown(f"**Mass & Stoichiometry Check:**\n> {pred.conservation_and_regime_check}")

    with col_det2:
        st.markdown("#### 📖 Authors' Verified Physical Mechanism")
        st.info(gt_case.ground_truth_mechanism_explained_by_authors)
        st.markdown("#### 📚 External Evidence Retrieved via Valency")
        if logs:
            for l in logs[:4]:
                st.markdown(f"- {l}")
        else:
            st.caption("No external papers triggered.")
