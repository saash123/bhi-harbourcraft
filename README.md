# BHI & Commingling Research Prototype — Poster Day

## Run on your computer
1. Install Python 3.10+.
2. Open a terminal in this folder.
3. `python -m pip install -r requirements.txt`
4. `python -m streamlit run app.py`
5. A browser dashboard will open. Use the three tabs: fuel screening, commingling, risk weights and validation.

## Verify the calculation engine
`python tests.py` — expected 16 passed.

## Poster material
- `POSTER_COPY.md`: complete research-facing poster wording, equations, findings and references.
- `BHI_Poster_Draft.pptx`: editable widescreen poster-style summary slide. Resize to your institution's physical poster dimensions if needed.

## Research safeguards
- No PSA Marine operational or laboratory measurements have been used.
- FMEA and MCDA numbers are researcher-assumed illustrative ratings. Independent expert assessment is outstanding.
- BHI scoring is not calibrated against real degradation data.
- Default water/TAN/oxidation thresholds are user-editable demonstration settings, not certified marine-fuel requirements. Confirm applicable ISO 8217 fuel grade before any real-world comparison.
- A threshold breach is an independent flag; BHI never overrides it.
- The Python program is a research demonstration, not an operational fuel release or maintenance authorisation tool.
