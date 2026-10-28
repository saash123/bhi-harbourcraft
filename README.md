# Integrated Biofuel Health Index Fleet System

An integrated Streamlit research prototype for simulated harbourcraft bunkering operations, supplier COQ reviews, compatibility evidence checks, fuel quantity and blend bookkeeping, representative sample BHI screening, alerts and Power BI-compatible exports.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Deploy to existing Streamlit Cloud repository

Replace the repository's old `app.py` and upload `core.py`, `fleet_db.py`, and `requirements.txt` at the repository root. Main file remains `app.py`, branch `main`.

## Sequence for the demonstration

1. Fleet Overview: review 5 synthetic tugboats and ten tanks.
2. Pre-bunkering & COQ: choose vessel/tank and inspect recorded ROB.
3. Compatibility & review: provide a COQ reference, vessel approval, documented compatibility evidence reference, reviewer, fuel blend and proposed quantity. Save review (must be complete to proceed).
4. Bunkering: select the reviewed event, enter actual ROB and volume, BDN and sample reference. Saving updates the tank and generates an outstanding test-review alert.
5. Fuel quality & BHI: enter a representative laboratory tank sample, test methods and measurements. The BHI uses provisional MCDA weights and separately checks reference thresholds.
6. Alerts & Power BI exports: review alert outcomes and export six related tables for Power BI Desktop. Scientific validation: inspect and vary MCDA criteria.

## Data and scientific limitations

- All seeded records and values are synthetic. Do NOT enter confidential company information into a public app.
- The local SQLite file (`fleet_demo.db`) is writable for demonstrations but **not reliable persistent production storage on Streamlit Community Cloud**; cloud containers may restart and reset it. Export data after demonstrations. Multiple public users could overwrite or view demo data. For an actual multi-user fleet, use an approved hosted PostgreSQL database, login/authorisation, event auditing, immutable evidence files and backups.
- The product has no integration with PSA Marine systems, certified laboratories, or Power BI online refresh. Power BI support is CSV export for manual import.
- Incoming supplier COQ results are not assigned to a commingled onboard tank. BHI is generated only from user-entered representative measurements, if provided.
- Mixing assumes uniform fuel composition, known volumes and FAME blend by volume. Effective age is bookkeeping, not a predictive chemical deterioration model. Existing tank inventory and age must be manually reconciled; no fuel consumption module is built.
- Evidence-checkbox review does not prove physical compatibility and is **not authorisation** to bunker or operate. Specialist fuel testing and vessel-specific approval remain necessary as relevant.
- The three BHI limits are **illustrative**, not a certified ISO 8217 fuel-grade profile. MCDA weights and 50%-limit penalty onset are exploratory engineering choices. Exceeding a numerical limit raises a separate alert even when BHI is high.
- No automated COQ-document verification, authentication, real-time sensor monitoring or laboratory validation has been implemented.

## Core files
- `app.py` — Streamlit interface
- `core.py` — original scientifically qualified BHI + fuel-age mathematics
- `fleet_db.py` — SQLite schema and transactions
- `test_system.py` — runnable workflow tests
- `requirements.txt` — dependencies

## Version 2.2 — Simpler user experience and reset

- Navigate with seven straightforward sections plus **Settings & reset**.
- Use the sidebar **Reset demo data** shortcut, then open **Settings & reset** to confirm.
- Reset requires ticking the irreversible-deletion checkbox and typing `RESET`. This clears all demonstration COQ reviews, bunkering records, samples, and alerts and restores five synthetic vessels with ten tanks.
- TG01 starts at **0 L and 0 days** in each tank to illustrate the first biofuel delivery. TG02–TG05 use **assumed 10/12/20/35-day** initial ages. The figures are not fuel deterioration thresholds.
- The app does not ask users to predict or certify a compatible resulting blend. Incoming-grade approval and COQ review remain documented checks. Any calculated mixture composition is for internal bookkeeping only.
- SQLite reset affects the current shared application database. Use CSV exports to retain demonstration records before resetting. Streamlit Community Cloud storage is not durable production storage.
