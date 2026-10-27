# Development of a Prototype Biofuel Health Index and Commingling Monitoring Framework for Harbour Craft
P Saashkintan | SIT Naval Architecture & Marine Engineering | PSA Marine (industry context)

## Background
Singapore's maritime sector is preparing for increased use of alternative marine fuels. ISO 8217:2024 includes marine fuel categories involving FAME blends. Biodiesel quality during storage and handling may be affected by water contamination and oxidation; acid number provides a complementary measure of deterioration.

## Problem / research gap
Harbour craft tanks may retain fuel between bunkering events, complicating fuel age traceability. A transparent, simple decision-support prototype could help visualise potential quality concerns without claiming to replace laboratory analysis. No PSA Marine fuel measurements or existing testing workflow were verified for this project.

## Objective
Develop and computationally verify a prototype that (1) tracks effective fuel age under a well-mixed commingling assumption, (2) computes a transparent preliminary Biofuel Health Index using water, TAN, and oxidation stability, and (3) flags individual reference-limit breaches independently of the composite score.

## Methodology
1. Literature review and risk identification: NREL (2023), ISO 8217:2024, MPA biofuel bunkering framework.
2. Illustrative FMEA: identify six fuel-related failure modes and prioritise them; ratings are hypothetical, not measured frequencies.
3. Independent MCDA: score water, TAN and oxidation stability for operational consequence, early-warning usefulness, monitoring practicality and evidence relevance, with user-adjustable inputs; normalise importance scores into BHI weights.
4. Python model: apply a bounded, provisional penalty based on the ratio of each measurement to a user-selected reference threshold. Keep reference-limit breach flags separate.
5. Streamlit demonstration: synthetic input sliders, effective-age computation, BHI gauge, comparison of weighting schemes, CSV export.
6. Verification: 16 automated tests on arithmetic invariants and rule boundaries. Sensitivity: evaluate the same fuel scenario using multiple weights.

## Governing equations
Effective fuel age: A_new = [V_ROB(A_old + Δt) + V_fresh A_fresh] / (V_ROB + V_fresh).
MCDA weight: w_i = 100 × weighted_criterion_score_i / sum(weighted_criterion_scores).
BHI = max(0, 100 − sum(w_i × penalty_i)), with independently applied reference-limit flags.

## Preliminary results (synthetic verification only)
- 16/16 computational tests passed.
- Example: 1,000 L at 20 days, 10 more days elapse, 800 L consumed and replaced by 800 L fresh fuel → effective age 6.0 days.
- At 5% remaining fuel, effective age is diluted but NOT reset automatically.
- BHI weights respond to editable MCDA scoring, demonstrating transparent design sensitivity.

## Limitations
No laboratory or operational samples were analysed. MCDA and FMEA ratings and penalty functions are researcher assumptions. Effective age is not a prediction of microbial concentration, oxidation stability or engine-failure probability. Default thresholds are illustrative and NOT universal ISO 8217 compliance limits. This is not a fuel release, maintenance or chemical dosing control system.

## Conclusion and future work
A functional, auditable Python decision-support prototype has been developed and mathematically verified with synthetic cases. Future work: supervisor review of risk ratings, confirmation of fuel-specific standard thresholds, and prospective comparison against actual laboratory results.

## References
McCormick, R. L. & Moriarty, K. (2023). Biodiesel Handling and Use Guide, Sixth Edition. NREL/TP-4A00-86939. https://doi.org/10.2172/2001221
ISO (2024). ISO 8217:2024 – Specifications of marine fuels. https://www.iso.org/standard/80579.html
MPA Singapore. Biofuel Bunkering. https://www.mpa.gov.sg/port-marine-ops/marine-services/bunkering/biofuel-bunkering
IEC (2018). IEC 60812:2018 – Failure modes and effects analysis (FMEA and FMECA).
