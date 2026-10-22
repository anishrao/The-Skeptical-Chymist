# OSI Hackathon Presentation Slide Deck (8 Slides, 5-Minute Pitch)

> **Tip:** An interactive browser-ready HTML slide deck has also been generated at [`doc/OSI_HACKATHON_SLIDES.html`](file:///Users/anishrao/Library/Mobile%20Documents/com~apple~CloudDocs/Pr_literature_gap_analyzer_Experiment_predictor/doc/OSI_HACKATHON_SLIDES.html) (open in Chrome/Safari and press `F` for full-screen presentation mode, use `←`/`→` arrow keys).

---

## Slide 1: Title & Core Vision
### **PerturbMat-Agent: Climbing the Scientific DIKW Pyramid with Adversarial Cross-Questioning Agents**
- **The Goal:** Move Scientific AI from **Literature Summarization (*Information*)** to **Counterfactual Experiment Prediction (*Wisdom*)**.
- **Testbed Domain:** Colloidal Gold Nanobipyramid (`AuBP`) Synthesis (`17` pre-2024 papers + paired SI files, `575` chunks, `22` causal edges).
- **Blinded Validation:** Tested against **all 8 experimental series (56 samples, 36 observables)** of a held-out 2024 paper (*Sánchez-Iglesias & Grzelczak, Small 2024*, `DOI: 10.1002/smll.202407735`).

---

## Slide 2: The Problem — The "Textbook Majority-Vote Trap"
### **Why Foundational LLMs & Single-Agent RAG Fail in the Lab**
- **Data $\to$ Information (`Mode 1: Standard RAG`):** Retrieves isolated paragraphs from PDFs, ignoring buried Supplementary Information (SI) tables and coupled conservation constraints.
- **Information $\to$ Knowledge (`Mode 2: CMO Graph` & `Mode 3: Generic Multi-Agent`):** Aggregates common trends across papers—**but confuses statistical frequency with physical law!**
- **The Trap:** Because $>90\%$ of plasmonic papers study single-crystal gold nanorods (where adding $\text{CTAB}$ *increases* aspect ratio and *red-shifts* LSPR), Single-Agent and Consensus Multi-Agent systems blindly predict the **exact opposite of reality** when applied to pentatwinned bipyramids in $\text{CTAC} + \text{8-HQL}$!

---

## Slide 3: Our Hypothesis & Architecture — Climbing to *Wisdom*
### **Adversarial Physical-Chemistry Cross-Questioning (`Mode 4`)**
- Instead of polite multi-agent consensus, we pit a **CMO-Grounded Proposer** against an **Adversarial Physical-Chemistry Skeptic**:
  1. **Mass & Stoichiometric Conservation Audit:** $V_{\text{particle}} \propto W^2 L \propto [\text{HAuCl}_4]/[\text{Au}^0_{\text{seed}}]$.
  2. **Nernst Redox Potential Audit ($E^0$):** $[\text{AuBr}_2]^-$ ($0.960\text{ V}$) vs. $[\text{AuCl}_2]^-$ ($1.154\text{ V}$).
  3. **Facet Complexation & Monolayer Saturation Audit:** $\text{CTA}^+/[\text{AgBr}_2]^-$ on $\{112\}$ facets & $1.0\text{ ML }\text{Ag}^+$ UPD threshold ($30\text{ }\mu\text{M}$).
  4. **Targeted Live Literature Verification:** Automated `OpenAlex` / `EuropePMC` queries with strict anti-leakage blacklisting (`Year < 2024`).

---

## Slide 4: Quantitative Proof on the DIKW Pyramid
### **4-Way Ablation Across All 8 Experimental Series (56 Samples) of the Held-Out 2024 Paper**

| DIKW Rung | Architecture Mode | Primary Benchmark Acc. (`Fig. 1`) | Full-Paper Acc. (`36 Observables`) | Mass Conservation Enforced? | Brier Error (↓) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Information** | **1. Single-Agent Standard RAG** | $14.3\%$ ($1/7$) | $77.8\%$ | ✅ Yes | $0.7225$ |
| **Knowledge** | **2. Single-Agent + Hybrid CMO Graph** | $33.3\%$ ($2/6$) | $38.9\%$ | ❌ No | $0.7744$ |
| **Knowledge** | **3. Generic Multi-Agent Discussion** | $28.6\%$ ($2/7$) | $38.9\%$ | ❌ No | $0.7225$ |
| **Wisdom (Ours)** | **4. Mechanistic Cross-Questioning Agent** | **$85.7\%$ ($6/7$)** | **$94.4\%$ ($34/36$)** | **✅ Yes ($100\%$)** | **$0.0025$** |

---

## Slide 5: Smoking-Gun #1 — The Centerpiece Experiment (`Figure 1` / `Table S1`)
### **Perturbation: Adding `1 to 50 mM CTAB` to `100 mM CTAC + 8-HQL` at Fixed Seeds (`[Au3+]/[Au0] = 67`)**
- **Single-Agent Prediction (`Modes 1 & 2`, $89\%$ Confidence):**
  - ❌ *"Bromide binds side facets $\to$ Length **increases** ($50 \to 120\text{ nm}$), Aspect Ratio **increases** ($2.5 \to 5.2$), Tips **sharpen**, Volume **increases $2.7\times$**, and LSPR **red-shifts** ($750 \to 950\text{ nm}$)."* (**$14.3\%$ Accuracy!**)
- **Our Cross-Questioning Skeptic (`Mode 4`) Intervenes:**
  - ⚡ **Law 1 (Mass Balance):** $[\text{HAuCl}_4]/[\text{Au}^0] = 67$ is constant $\implies$ **Single-particle volume MUST stay constant ($\sim 11,000\text{ nm}^3$)**, so $L$ and $W^2$ must move oppositely!
  - ⚡ **Law 2 & 3 (Redox & $\{112\}$ Passivation):** $E^0([\text{AuBr}_2]^-) = 0.960\text{ V} < E^0([\text{AuCl}_2]^-) = 1.154\text{ V}$ slows reduction **$10\times$ ($30 \to 350\text{ min}$)** and $\text{CTA}^+/[\text{AgBr}_2]^-$ passivates $\{112\}$ twin-tip facets $\implies$ **Length decreases ($100 \to 49\text{ nm}$), Width increases ($17 \to 29\text{ nm}$), Aspect Ratio drops ($5.9 \to 1.7$), Tips blunt, and LSPR blue-shifts $486\text{ nm}$ ($1070 \to 584\text{ nm}$)!**

---

## Slide 6: Smoking-Gun #2 — The 30-Day Shelf-Life Paradox (`Figure S18`) & Seed Sweep (`Figure 3`)
### **Two More Cases Where Single-Agent Fails & Cross-Questioning Wins**
1. **30-Day Storage Stability in `10 mM CTAB` vs. `10 mM CTAC` (`EXP_8` / `Fig. S18`):**
   - **Single-Agent (`Mode 2`):** ❌ *"CTAB has a denser bilayer, so `CTAB` is stable ($<10\text{ nm}$ shift) and `CTAC` degrades ($>100\text{ nm}$ blue-shift)."*
   - **Our Agent (`Mode 4`):** ✅ Lower redox potential of $[\text{AuBr}_2]^-$ ($0.960\text{ V}$) allows dissolved $\text{O}_2$ to oxidize sharp tips in `CTAB` $\implies$ Predicted **$42\text{–}48\text{ nm}$ blue-shift in `CTAB`** and **$0\text{ nm}$ shift in `CTAC`**.
   - **Actual Lab Result (`Fig. S18`):** **`CTAB` blue-shifts $45\text{ nm}$ ($900 \to 855\text{ nm}$); `CTAC` shifts $0\text{ nm}$!**
2. **10-Fold Seed Concentration Sweep (`EXP_5` / `Table S4`, $2.5 \to 25\text{ }\mu\text{M}$):**
   - **Single-Agent (`Mode 2`):** ❌ Assumes self-similar scaling (constant $AR = 3.0$, constant $\lambda = 750\text{ nm}$).
   - **Our Agent (`Mode 4`):** ✅ Catches per-particle monomer flux depletion $\implies$ **Both volume ($14,000 \to 2,300\text{ nm}^3$) AND aspect ratio ($4.7 \to 2.2$) drop, blue-shifting LSPR ($976 \to 635\text{ nm}$)!**

---

## Slide 7: Literature Gap Discovery (`Task 1`)
### **Discovering the Held-Out Paper's Core Innovation from Pre-2024 Papers Alone**
- **Single-Agent Gaps:** Suggested routine 1D sweeps already in SI tables or unphysical sub-$1\text{ }\mu\text{L}$ seed dilutions (which cause burst sphere nucleation).
- **Cross-Questioning Gaps (`Mode 4`, Specificity $9/10$):**
  - Pruned unphysical proposals via LaMer nucleation checks.
  - Identified the **exact 2D orthogonal co-perturbation (`[Seeds]` $\times$ `[CTAB]`) required to tune single-particle volume 6-fold ($3,110 \to 19,702\text{ nm}^3$) at a fixed $750\text{ nm}$ LSPR**—the exact breakthrough reported in `Figure 5` of the held-out 2024 *Small* paper!

---

## Slide 8: Beyond Retrospective Validation — Prospective Wet-Lab Co-Pilot
### **New Falsifiable Predictions Ready for the Lab**
- **The "Surface-Area-Scaled $\text{Ag}^+$ Cliff" in Minibipyramids:**
  - Because total nanoparticle surface area scales as $A_{\text{total}} \propto N_{\text{seeds}}^{+1/3}$ at constant $[\text{HAuCl}_4]$, pushing seed concentration to $42\text{ }\mu\text{M}$ (for $V \approx 1,400\text{ nm}^3$ absorption-dominant minibipyramids) drops the "universal" $30\text{ }\mu\text{M }\text{AgNO}_3$ below $1.0\text{ monolayer}$—whereas **$60\text{ }\mu\text{M }\text{AgNO}_3$ rescues $>92\%$ shape purity**!
- **Takeaway:** Adversarial Physical-Chemistry Cross-Questioning turns LLMs from **literature parrots (*Information/Knowledge*)** into **first-principles scientific co-pilots (*Wisdom*)**.
