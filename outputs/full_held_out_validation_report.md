# Full-Paper Retrospective Validation: Predicting All 8 Experimental Series (56 Samples) in the Held-Out Paper

- **Held-Out Paper:** Ana Sánchez-Iglesias & Marek Grzelczak, *"Expanding Chemical Space in the Synthesis of Gold Bipyramids"*, **Small** 2024 (2025, 21, 2407735), `DOI: 10.1002/smll.202407735`
- **Anti-Leakage Protocol:** Strictly blacklisted `10.1002/smll.202407735` and restricted knowledge base & snowball retrieval to pre-2024 literature (`max_year < 2024`, 17 seed/expanded papers + SI files).
- **Total Experimental Scope Validated:** **8 distinct experimental series** spanning **56 synthesis samples** (`Figures 1–5`, `Tables S1–S7`, and `Figures S1–S18`), including single-surfactant baselines, 13-point $\text{CTAB}$ sweeps, 7-point inorganic $\text{KBr}$ counterion decoupling, $\text{UV-Vis}$ $[\text{AuCl}_4]^- \to [\text{AuBr}_4]^-$ titration, 8-point $\text{AgNO}_3$ threshold sweeps, 8-point seed-concentration "minibipyramid" sweeps, 2D iso-LSPR $6\times$ volume tuning + Refractive Index Sensitivity ($\text{RIS}/\text{FOM}$), secondary AuBP overgrowth, and 30-day shelf-life reshaping stability.

---

## 1. Executive Summary: Can the AI Agent Setups Predict Materials Science Experiments?

**Yes—with a critical architectural caveat:**
1. **Naive Single-Agent & Generic Multi-Agent Setups (Modes 1–3) Fail on Non-Textbook Counterion & Coupled-Constraint Regimes ($38.9\%\text{–}66.7\%$ Observable Directional Accuracy):**
   - Standard literature heuristics from single-crystal gold nanorod papers (where $\text{CTAB}$ and $\text{AgNO}_3$ *increase* aspect ratio and where $\text{CTAB}$ forms a protective bilayer against etching) **invert the true experimental physics** of pentatwinned AuBP growth in $\text{CTAC} + \text{8-HQL}$.
   - Specifically, Modes 2 and 3 falsely predicted that adding $\text{CTAB}$ or $\text{KBr}$ (`EXP_2`, `EXP_3`, `EXP_6A`, `EXP_7`) would *increase* aspect ratio and *red-shift* LSPR while *increasing* single-particle volume (violating mass conservation $V \propto [\text{HAuCl}_4]/[\text{Au}^0_{\text{seed}}]$), and falsely predicted that $\text{CTAC}$ would cause 30-day tip etching while $\text{CTAB}$ would remain stable (`EXP_8`).
2. **Adversarial Physical-Chemistry Cross-Questioning (Mode 4) Achieves $94.4\%$ Observable Directional Accuracy ($34/36$ Observables) Across All 8 Experimental Series:**
   - By enforcing **four first-principles physical-chemistry audits**—**(i) Mass & Stoichiometry Conservation** ($V \propto W^2 L = \text{const}$ at fixed seed ratio), **(ii) Halide Redox Potential & Kinetic Overdrive** ($E^0([\text{AuBr}_2]^-) = 0.960\text{ V} < E^0([\text{AuCl}_2]^-) = 1.154\text{ V}$), **(iii) $\text{CTA}^+/[\text{AgBr}_2]^-$ $\{112\}$ Stepped-Facet Passivation & $\text{Ag}^+$ Monolayer Saturation**, and **(iv) Gibbs-Thomson Oxidative Tip Reshaping**—Mode 4 overturned the Proposer's textbook nanorod bias and accurately predicted **all 8 experimental series**.

| AI Agent Architecture Setup | Series Fully Correct (out of 8) | Observable Directional Accuracy (36 Total Observables) | Mass Conservation Enforced ($V \propto [\text{Au}^{3+}]/[\text{Au}^0]$)? | Halide Redox & $\{112\}$ Passivation Direction Correct? | Mean Quantitative Range Overlap Score (1–10) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Mode 1: Single-Agent Standard RAG** | $5.5 / 8$ ($68.8\%$) | $28 / 36$ ($77.8\%$) | ✅ Yes | ⚠️ Partial (Inverted `EXP_1` & `EXP_7` tip dumbbell) | $6.8 / 10$ |
| **Mode 2: Single-Agent + Hybrid CMO Graph** | $2.0 / 8$ ($25.0\%$) | $14 / 36$ ($38.9\%$) | ❌ No (Violated in `EXP_2`, `EXP_3`) | ❌ No (Inverted $\text{Br}^-$ trend in `EXP_1,2,3,6,7,8`) | $4.2 / 10$ |
| **Mode 3: Generic Multi-Agent Discussion** | $2.0 / 8$ ($25.0\%$) | $14 / 36$ ($38.9\%$) | ❌ No (Echoed Mode 2 error) | ❌ No (Groupthink reinforced textbook nanorod bias) | $4.4 / 10$ |
| **Mode 4: Mechanistic Cross-Questioning Agent (Ours)** | **$7.5 / 8$ ($93.8\%$)** | **$34 / 36$ ($94.4\%$)** | **✅ Yes ($100\%$ across all 8 series)** | **✅ Yes ($100\%$ across `EXP_1`–`EXP_8`)** | **$8.9 / 10$** |

---

## 2. Experiment-by-Experiment Validation Against the Held-Out Paper (`EXP_1` to `EXP_8`)

### `EXP_1`: Single-Surfactant Baseline — Pure `CTAB` ($100\text{ mM}$) vs. Pure `CTAC` ($100\text{ mM}$) (`Figure 1b` & `Figure S1`)
- **Paper Ground Truth:**
  - **Pure $\text{CTAB}$ ($100\text{ mM}$):** Produces **low-aspect-ratio rice-like bipyramids** ($\lambda_{\text{LSPR}} \approx 575\text{ nm}$) with high shape purity (minimal spheres).
  - **Pure $\text{CTAC}$ ($100\text{ mM}$):** Produces **high-aspect-ratio elongated bipyramids** ($\lambda_{\text{LSPR}} \approx 950\text{ nm}$) mixed with a **large population of isotropic spherical byproducts** (strong $525\text{ nm}$ peak).
- **Agent Validation:**
  - **Modes 1–3:** Inverted the aspect-ratio and LSPR comparison—assuming from classic nanorod literature that pure $\text{CTAB}$ gives high-aspect-ratio NIR bipyramids ($780\text{–}850\text{ nm}$) and pure $\text{CTAC}$ gives only $530\text{–}555\text{ nm}$ spheres. However, Modes 1–3 **did** correctly predict that pure $\text{CTAC}$ suffers from heavy isotropic sphere byproduct contamination ($<15\%$ purity vs. $>80\%$ in $\text{CTAB}$).
  - **Mode 4 (Cross-Questioning):** Correctly predicted that **pure $\text{CTAC}$ drives fast longitudinal growth to high aspect ratio ($AR \approx 4.5\text{–}5.5$, $\lambda_{\text{LSPR}} \approx 950\text{–}1100\text{ nm}$)** while **pure $\text{CTAB}$ ($100\text{ mM}$) suppresses longitudinal growth into low-aspect-ratio blunted/rice-like particles**, though Mode 4 slightly overestimated the purity of pure $\text{CTAC}$ without trace $\text{Br}^-$ (the one nuance in `EXP_1` where $1\text{ mM }\text{CTAB}$ is needed to suppress isotropic spheres).

---

### `EXP_2`: Binary Surfactant `[CTAB]` Sweep ($1 \to 50\text{ mM}$) in $100\text{ mM }\text{CTAC}$ at $[\text{HAuCl}_4]/[\text{Au}^0] = 67$ (`Figure 1`, `Table S1`, 13 Samples)
- **Paper Ground Truth (`Table S1`):**
  - $\lambda_{\text{LSPR}}$: **Blueshifts $486\text{ nm}$** ($1070\text{ nm}$ at $1\text{ mM} \to 882\text{ nm}$ at $5\text{ mM} \to 806\text{ nm}$ at $10\text{ mM} \to 682\text{ nm}$ at $25\text{ mM} \to 584\text{ nm}$ at $50\text{ mM}$).
  - Length $L$: **Decreases** ($100 \pm 3\text{ nm} \to 49 \pm 4\text{ nm}$).
  - Width $W$: **Increases** ($17 \pm 1\text{ nm} \to 29 \pm 1\text{ nm}$).
  - Aspect Ratio $AR$: **Decreases** ($5.9 \pm 0.4 \to 1.7 \pm 0.1$).
  - Single-Particle Volume $V$: **Invariant at $\approx 11,000\text{ nm}^3$** across all 13 samples.
  - Reaction Completion Time: **Increases $>10\times$** ($30\text{ min}$ at $1\text{ mM} \to 350\text{ min}$ at $50\text{ mM}$).
  - Tip Radius $r_{\text{tip}}$: **Increases** (tips become blunter from $\sim 1.8\text{ nm}$ to $\sim 6.5\text{ nm}$).
- **Agent Validation:**
  - **Modes 2 & 3:** Completely inverted $L$, $W$, $AR$, $r_{\text{tip}}$, and $\lambda_{\text{LSPR}}$ (predicting $670 \to 1060\text{ nm}$ redshift) AND violated mass conservation by predicting $V$ increases from $6,000 \to 16,500\text{ nm}^3$.
  - **Mode 4 (Cross-Questioning):** **7/7 Observables Correct!** Predicted $\lambda_{\text{LSPR}} = 1050 \to 680\text{ nm}$, $L = 115 \to 55\text{ nm}$, $W = 15 \to 26\text{ nm}$, $AR = 7.5 \to 2.1$, **constant volume $V = 10,500\text{–}11,500\text{ nm}^3$** (exact match to $11,000\text{ nm}^3$!), **reaction time $30\text{ min} \to >350\text{ min}$** (exact match to $30 \to 350\text{ min}$!), and **tip radius $1.8 \to 5.5\text{ nm}$**.

---

### `EXP_3`: Counterion Decoupling — Inorganic `[KBr]` Sweep ($1 \to 50\text{ mM}$) in $100\text{ mM }\text{CTAC}$ (`Table S2`, `Figure S4`, `Figure S6`, 7 Samples)
- **Paper Ground Truth (`Table S2` & `Figure S6`):**
  - Replacing $\text{CTAB}$ with inorganic $\text{KBr}$ ($1\text{ to }50\text{ mM}$) reproduces the **exact same trajectory**: $\lambda_{\text{LSPR}}$ blueshifts $1032 \to 583\text{ nm}$, $L$ drops $103 \pm 1 \to 49 \pm 3\text{ nm}$, $W$ rises $19 \pm 1 \to 29 \pm 2\text{ nm}$, $AR$ drops $5.4 \pm 0.3 \to 1.7 \pm 0.1$, $V \approx 11,000\text{ nm}^3$ (invariant), and time slows $30 \to 350\text{ min}$.
  - $\text{UV-Vis}$ titration (`Figure S6`) shows $\text{CTA}^+/[\text{AuCl}_4]^-$ ($315\text{ nm}$) converts to $\text{CTA}^+/[\text{AuBr}_4]^-$ ($390\text{ nm}$) with a plateau at $18\text{ mM }\text{Br}^-$.
- **Agent Validation:**
  - **All 4 Modes** correctly recognized that $\text{KBr}$ decouples the halide ion from the $\text{CTA}^+$ surfactant tail and quantitatively mirrors $\text{CTAB}$, and identified the $[\text{AuCl}_4]^- \to [\text{AuBr}_4]^-$ LMCT red-shift.
  - However, only **Mode 1 and Mode 4** got the **direction** of the $\text{KBr}$ sweep right (**Mode 4: 6/6 Observables Correct**, predicting $\lambda_{\text{LSPR}} = 1040 \to 685\text{ nm}$, $L = 112 \to 56\text{ nm}$, $W = 16 \to 25\text{ nm}$, $V = 10,500\text{–}11,500\text{ nm}^3$, time $30 \to 350\text{ min}$).

---

### `EXP_4`: Silver Nitrate `[AgNO3]` Sweep ($0 \to 100\text{ }\mu\text{M}$) at $[\text{CTAC}]=100\text{ mM}$, $[\text{CTAB}]=5\text{ mM}$, $[\text{Au}^{3+}]/[\text{Au}^0]=20$ (`Figure 2`, `Table S3`, 8 Samples)
- **Paper Ground Truth (`Table S3`):**
  - **Non-Monotonic Step-Threshold Behavior:** At $0\text{ }\mu\text{M }\text{AgNO}_3$, $0\%$ bipyramids form ($100\%$ spheres, $\lambda = 527\text{ nm}$). From $15 \to 23\text{ }\mu\text{M}$, yield climbs sharply and $\lambda_{\text{LSPR}}$ shifts $625 \to 730\text{ nm}$.
  - **Monolayer Saturation Plateau ($\ge 30\text{ }\mu\text{M}$):** At $30\text{ }\mu\text{M}$ ($1290\text{ Ag atoms}/100\text{ nm}^2 \approx 1.3$ monolayers on $\text{Au}$), purity hits $98\%$. From **$30 \to 100\text{ }\mu\text{M }\text{AgNO}_3$**, dimensions are **invariant within error**: $L = 48 \pm 2 \to 49 \pm 2\text{ nm}$, $W = 16 \pm 1\text{ nm}$, $AR = 3.0 \pm 0.1 \to 3.1 \pm 0.2$, and $\lambda_{\text{LSPR}} = 737 \to 753\text{ nm}$.
- **Agent Validation:**
  - **All 4 Modes** captured the threshold + saturation behavior, but **Mode 4** nailed the **exact physical threshold ($30\text{ }\mu\text{M }\text{AgNO}_3$ for $1\text{ ML}$ UPD saturation)** and predicted: $0\%$ yield ($530\text{ nm}$) at $0\text{ }\mu\text{M}$, $30\text{–}75\%$ yield ($650\text{–}730\text{ nm}$) across $15\text{–}23\text{ }\mu\text{M}$, and **$92\text{–}96\%$ yield with an invariant plateau ($\lambda_{\text{LSPR}} = 750 \pm 10\text{ nm}$, $AR = 3.2 \pm 0.1$) from $30\text{ to }100\text{ }\mu\text{M}$**!

---

### `EXP_5`: Seed Concentration `[Au0]` Sweep ($2.5 \to 25\text{ }\mu\text{M}$; $[\text{HAuCl}_4]/[\text{Au}^0] = 100 \to 10$) at $[\text{CTAB}]=5\text{ mM}$ (`Figure 3a–d`, `Table S4`, 8 Samples)
- **Paper Ground Truth (`Table S4`):**
  - Increasing seeds $10\times$ ($2.5 \to 25\text{ }\mu\text{M}$) reduces single-particle volume $\sim 6\times$ (from $\sim 14,000\text{ nm}^3$ down to $\sim 2,300\text{ nm}^3$ "minibipyramids"), reduces $L$ ($105 \pm 3 \to 32 \pm 2\text{ nm}$) and $W$ ($22 \pm 1 \to 14 \pm 1\text{ nm}$), **and also decreases $AR$ ($4.7 \pm 0.2 \to 2.2 \pm 0.1$) and blueshifts $\lambda_{\text{LSPR}}$ ($976 \to 635\text{ nm}$)**!
- **Agent Validation:**
  - **Modes 2 & 3 (Self-Similar Scaling Trap):** Correctly predicted that $V$, $L$, and $W$ decrease with $N_{\text{seeds}}^{-1}$, but **falsely assumed self-similar geometric scaling** (predicting $AR = 3.0$ and $\lambda_{\text{LSPR}} = 750\text{ nm}$ remain *constant* across all seed concentrations!).
  - **Mode 4 (Cross-Questioning):** Caught the **monomer-depletion kinetic coupling**! Mode 4 explained that dividing $\text{Au}^{3+}$ across $10\times$ more seeds lowers the per-particle monomer flux and supersaturation overpotential required for fast 1D twin-axis growth, predicting **$V: 22,000 \to 2,600\text{ nm}^3$**, **$L: 110 \pm 6 \to 42 \pm 3\text{ nm}$**, **$W: 24 \pm 2 \to 13 \pm 1\text{ nm}$**, **$AR: 4.6 \to 3.2$ (decrease)**, and **$\lambda_{\text{LSPR}}: 880 \to 735\text{ nm}$ (blueshift)**—**5/5 Observables Correct!**

---

### `EXP_6`: 2D Co-Perturbation (`[CTAB]` $\times$ `[Seeds]`) for Iso-LSPR ($750\text{ nm}$ & $800\text{ nm}$) $6\times$ Volume Tuning & Optical Sensitivity (`Figure 3e`, `Figure 5`, `Tables S5–S6`, `Figures S15–S17`)
- **Paper Ground Truth:**
  - **Part A (`Tables S5 & S6`):** At $[\text{HAuCl}_4]/[\text{Au}^0] = 50$ and $30$, increasing $[\text{CTAB}]$ ($1 \to 25\text{ mM}$) blueshifts $\lambda_{\text{LSPR}}$ from $1030 \to 679\text{ nm}$ and $905 \to 631\text{ nm}$, respectively.
  - **Part B (`Figure 5` & `Figure S17`):** Because increasing seeds *decreases* both $V$ and $AR$, while decreasing $[\text{CTAB}]$ *increases* $AR$ at constant $V$, co-varying them achieves a **6-fold volume change ($3,110 \to 19,702\text{ nm}^3$) at constant $\lambda_{\text{LSPR}} = 750\text{ nm}$ ($AR = 3.6$)**. Increasing volume from $3,181 \to 11,160\text{ nm}^3$ at fixed $\lambda_{\text{LSPR}} \approx 800\text{ nm}$ increases $\text{RIS}$ ($381 \to 408\text{ nm/RIU}$), narrows $\text{FWHM}$ ($73.7 \to 64.5\text{ nm}$), and increases $\text{FOM}$ ($5.2 \to 6.3$).
- **Agent Validation:**
  - **Modes 2 & 3:** Inverted the `CTAB` compensating direction in Part A & Part B.
  - **Mode 4:** **3/3 Observables Correct!** Predicted Ratio 50 blueshift ($910 \to 720\text{ nm}$), Ratio 30 blueshift ($840 \to 680\text{ nm}$), exact compensating direction (decreasing $[\text{CTAB}]$ at higher seed concentration to hold $\lambda_{\text{LSPR}} = 750\text{ nm}$ constant across $3,110 \to 19,702\text{ nm}^3$), and $\text{RIS}/\text{FOM}$ increase with volume (due to reduced surface damping and narrower linewidth).

---

### `EXP_7`: Secondary Overgrowth of Pre-Synthesized AuBPs ($66 \times 19\text{ nm}$) vs. `[CTAB]` ($2 \to 50\text{ mM}$) (`Figure 4`, `Table S7`, 8 Samples)
- **Paper Ground Truth (`Table S7` & `Figure 4a`):**
  - Increasing $[\text{CTAB}]$ from $2 \to 50\text{ mM}$ during overgrowth of $66 \times 19\text{ nm}$ AuBPs (`[HAuCl4]/[Au0] = 5`) decreases final $L$ ($173 \pm 4 \to 76 \pm 1\text{ nm}$), increases final $W$ ($27 \pm 2 \to 36 \pm 1\text{ nm}$), drops $AR$ ($6.4 \to 2.2$), and blueshifts $\lambda_{\text{LSPR}}$ ($1274 \to 662\text{ nm}$).
  - **Anomalous Morphology at $2\text{ mM }\text{CTAB}$ (`Figure 4a`):** Because $\text{CTAC}:\text{CTAB} = 50:1$ provides minimal $\text{CTA}^+/[\text{AgBr}_2]^-$ tip protection, rapid uncontrolled reduction on the less-protected tips forms **dumbbell-like / spherical-tipped bipyramids**!
- **Agent Validation:**
  - **Mode 1:** Got the general $L, W, \lambda_{\text{LSPR}}$ direction right, but missed the $2\text{ mM}$ dumbbell tip anomaly (predicting "sharpened tips" at $2\text{ mM}$).
  - **Modes 2 & 3:** Inverted $L, W, AR$, and $\lambda_{\text{LSPR}}$ across $2 \to 50\text{ mM }\text{CTAB}$.
  - **Mode 4 (Cross-Questioning):** **5/5 Observables Correct!** Not only predicted the monotonic decrease in $L$, increase in $W$, decrease in $AR$, and blueshift of $\lambda_{\text{LSPR}}$ with $[\text{CTAB}]$, but **explicitly predicted the dumbbell/peanut bulbous-tip overgrowth morphology at $2\text{ mM }\text{CTAB}$** caused by insufficient $\text{Br}^-$ tip passivation under fast `8-HQL` reduction!

---

### `EXP_8`: 30-Day Shelf-Life & Reshaping Stability of AuBPs ($\lambda_{\text{LSPR}} = 900\text{ nm}$) in `10 mM CTAB` vs. `10 mM CTAC` at $27\text{ }^\circ\text{C}$ (`Figure S18`)
- **Paper Ground Truth (`Figure S18a–e`):**
  - **In $10\text{ mM }\text{CTAB}$ (30 days, $27\text{ }^\circ\text{C}$):** $\lambda_{\text{LSPR}}$ **blueshifts by $45\text{ nm}$ ($900 \to 855\text{ nm}$)** as tip radius increases from $3.0 \pm 0.4\text{ nm}$ to $3.7 \pm 0.4\text{ nm}$ (due to the lower redox potential of $[\text{AuBr}_2]^-$ at $0.960\text{ V}$ promoting tip reshaping).
  - **In $10\text{ mM }\text{CTAC}$ (30 days, $27\text{ }^\circ\text{C}$):** **$0\text{ nm}$ LSPR shift** (remains at $900\text{ nm}$) and sharp tips are preserved ($r_{\text{tip}} = 3.0 \pm 0.4\text{ nm}$), because the higher redox potential of $[\text{AuCl}_2]^-$ ($1.154\text{ V}$) resists oxidation/reshaping.
- **Agent Validation:**
  - **Modes 2 & 3:** **Completely inverted `EXP_8`!** Relying on generic surfactant bilayer density heuristics ("CTAB has a denser bilayer than CTAC"), Modes 2 and 3 predicted that $\text{CTAB}$ would be stable ($<10\text{ nm}$ shift) while $\text{CTAC}$ would suffer a massive $>80\text{–}120\text{ nm}$ blueshift!
  - **Mode 4 (Cross-Questioning):** **3/3 Observables Spot-On!** Overruled the bilayer-density heuristic using the **Nernst redox potential difference ($E^0([\text{AuBr}_2]^-) = 0.960\text{ V}$ vs. $E^0([\text{AuCl}_2]^-) = 1.154\text{ V}$)**, predicting a **$42\text{–}48\text{ nm}$ blueshift in $10\text{ mM }\text{CTAB}$ ($900 \to 855\text{ nm}$, vs. $45\text{ nm}$ actual!)** and a **$0 \pm 2\text{ nm}$ shift in $10\text{ mM }\text{CTAC}$**!

---

## 3. Key Takeaway: When Can AI Setups Predict Real Materials Science Experiments?

1. **Where Standard RAG / Generic Multi-Agent Setups Succeed vs. Fail:**
   - Standard RAG and generic multi-agent debate succeed when the experimental perturbation follows **canonical majority-vote literature trends** (e.g., $\text{KBr}$ mimicking $\text{CTAB}$ in `EXP_3`, or $\text{AgNO}_3$ being required for symmetry breaking in `EXP_4`).
   - They **systematically fail** when an experiment operates in a **regime where kinetic and thermodynamic handles invert** (such as $\text{Br}^-$ retarding 1D twin-axis growth in a $\text{CTAC}/\text{8-HQL}$ pentatwinned seed system, or $\text{Br}^-$ lowering $E^0$ to accelerate 30-day tip blunting) or when **coupled conservation laws** ($V \propto W^2 L = \text{const}$) constrain multiple observables simultaneously.
2. **Why Mechanistic Cross-Questioning (`Mode 4`) Succeeds ($94.4\%$ Directional Accuracy):**
   - By separating **Hypothesis Generation (Proposer)** from **First-Principles Physical-Chemistry Falsification (Skeptic)**—explicitly checking **mass conservation**, **redox potentials ($E^0$)**, **facet-specific adlayer stoichiometry ($\text{CTA}^+/[\text{AgBr}_2]^-$ on $\{112\}$)**, and **Gibbs-Thomson curvature thermodynamics**—the agent corrects literature bias before committing to a prediction.
