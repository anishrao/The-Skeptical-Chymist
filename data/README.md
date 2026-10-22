# Dataset Folders for Gold Bipyramid Synthesis & Held-Out Evaluation

Place your PDFs into the folders below:

1. **`data/seed_papers/`**
   - Drop your **9–20 seed research papers** (PDF format) here.
   - Example: `2015_ Chateau_AuBipyramids.pdf`, `2017_SanchezIglesias_PentatwinnedSeeds.pdf`, etc.

2. **`data/seed_papers/supplementary_info/`**
   - Drop any **Supplementary Information (SI)** PDFs corresponding to your seed papers here.
   - *Tip:* Name each SI file with the same prefix as its main paper (e.g., `2015_Chateau_AuBipyramids_SI.pdf`) so the ingestion pipeline automatically links the SI recipes, tables, and characterization data to the parent paper! (You can also drop SI files directly into `data/seed_papers/` with `_SI` or `supp` in the filename).

3. **`data/held_out_papers/`**
   - Drop the **recent / held-out paper(s)** (and their SI, if applicable) whose experimental outcomes you want the agent to predict.
   - **Strict Anti-Leakage Handling:**
     - The agent knowledge base and literature snowball search **never** index this folder.
     - Instead, our `HeldOutExtractor` parses the held-out paper to extract:
       1. **The Blinded Experimental Setup & Perturbation Prompt** (only the starting recipe and the condition $X$ that was varied—stripping all results, outcomes, and discussions).
       2. **The Ground-Truth Outcome** (kept strictly hidden until after all agent architectures have locked in their predictions, then used to score accuracy).
     - Any external OpenAlex / EuropePMC literature search automatically blacklists the held-out paper's DOI, title, and any paper published after its publication date (or citing it).

4. **`data/expanded_papers/`**
   - Automatically populated by the **Citation Snowball & Active Literature Search Engine** when the agent discovers missing foundational papers or queries external literature during cross-questioning.
