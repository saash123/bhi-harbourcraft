"""Simplified BHI fleet monitor — synthetic research demonstrator only."""
import os
import io
import zipfile
from datetime import date

import pandas as pd
import streamlit as st

from core import (
    mcda_weights,
    DEFAULT_MCDA,
    CRITERIA,
    PARAMETERS,
    FMEA,
    calculate_bhi,
    ILLUSTRATIVE_LIMITS,
)
from fleet_db import (
    connect,
    seed,
    rows,
    tank,
    record_check,
    record_bunkering,
    record_sample,
    update_alert,
)

st.set_page_config(page_title="BHI Fleet Monitor", layout="wide", page_icon="⚓")

CSS = """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
[data-testid="stMetricValue"] {font-size: 2.2rem;}
.small-note {font-size: 0.92rem; opacity: 0.85;}
.section-card {
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    padding: 1rem 1rem 0.8rem 1rem;
    margin-bottom: 1rem;
    background: rgba(255,255,255,0.02);
}
.hero-box {
    border-radius: 16px;
    padding: 1rem 1.15rem;
    background: rgba(70,110,255,0.12);
    border: 1px solid rgba(70,110,255,0.25);
    margin-bottom: 1rem;
}
.soft-box {
    border-radius: 12px;
    padding: 0.9rem 1rem;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 0.75rem;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

DB_PATH = os.environ.get("BHI_DB_PATH", "fleet_demo.db")
cn = connect(DB_PATH)
seed(cn)
weights = mcda_weights()
limits = ILLUSTRATIVE_LIMITS.copy()
vessels = rows(cn, "SELECT * FROM vessels ORDER BY id")


def vessel_max(vessel_id):
    return next(v["approved_max_fame"] for v in vessels if v["id"] == vessel_id)


def pick_vessel_and_tank(key_prefix: str):
    vessel_id = st.selectbox("Vessel", [v["id"] for v in vessels], key=f"{key_prefix}_v")
    tank_rows = rows(cn, "SELECT * FROM tanks WHERE vessel_id=? ORDER BY name", (vessel_id,))
    tank_id = st.selectbox(
        "Tank",
        [r["id"] for r in tank_rows],
        format_func=lambda x: next(r["name"] for r in tank_rows if r["id"] == x),
        key=f"{key_prefix}_t",
    )
    return vessel_id, tank(cn, tank_id)


def show_tank_snapshot(vessel_id, t):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ROB", f"{t['volume_l']:,.0f} L")
    c2.metric("Tank capacity", f"{t['capacity_l']:,.0f} L")
    c3.metric("Recorded fuel", f"B{t['blend_pct']:.1f}")
    c4.metric("Effective fuel age", f"{t['age_days']:.2f} d")
    st.caption(
        f"Vessel recorded maximum approved biodiesel blend: B{vessel_max(vessel_id):.0f}. "
        "Use only synthetic data in this public demo."
    )


def dataframe_or_message(df, message="No records yet."):
    if df.empty:
        st.info(message)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


with st.sidebar:
    st.markdown("## Navigation")
    page = st.radio(
        "Go to",
        [
            "Overview",
            "1 · Pre-bunkering",
            "2 · Incoming fuel review",
            "3 · Bunkering record",
            "4 · Tank sample & BHI",
            "5 · Alerts & exports",
            "6 · Scientific basis",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    with st.expander("Screening reference values", expanded=True):
        st.caption("Illustrative research values only — not certified ISO/EN limits.")
        limits["Water"] = st.number_input("Water max (mg/kg)", min_value=0.01, value=500.0, step=10.0)
        limits["TAN"] = st.number_input("TAN max (mg KOH/g)", min_value=0.001, value=0.50, step=0.05)
        limits["Oxidation"] = st.number_input("Oxidation min (h)", min_value=0.01, value=8.0, step=0.5)
    st.caption("Keep real vessel approvals and actual marine-fuel specifications under qualified review.")

st.title("Biofuel Health Index · Fleet Management")
st.caption("Simple fleet workflow for bunkering, fuel-age tracking and tank-sample screening | SYNTHETIC DATA ONLY")
st.markdown(
    """
<div class="hero-box">
<b>This is a research demonstrator, not an operational approval system.</b><br>
Use the app to document: (1) incoming fuel review, (2) completed bunkering, (3) tank-sample results,
 and (4) fleet alerts. The app does <b>not</b> certify fuel safety or replace existing bunkering procedures.
</div>
""",
    unsafe_allow_html=True,
)

if page == "Overview":
    st.subheader("Fleet overview")
    snapshot = rows(
        cn,
        """
        SELECT t.*, 
            (SELECT s.bhi FROM samples s WHERE s.tank_id=t.id ORDER BY s.id DESC LIMIT 1) AS last_bhi,
            (SELECT s.status FROM samples s WHERE s.tank_id=t.id ORDER BY s.id DESC LIMIT 1) AS last_status
        FROM tanks t
        ORDER BY t.vessel_id, t.name
        """,
    )
    open_alerts = cn.execute("SELECT COUNT(*) FROM alerts WHERE status!='Closed'").fetchone()[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Vessels", len(vessels))
    m2.metric("Tanks monitored", len(snapshot))
    m3.metric("Open / under-review alerts", open_alerts)

    frame = pd.DataFrame(snapshot)
    if not frame.empty:
        frame["Condition status"] = frame["last_status"].fillna("UNVERIFIED — NO TANK SAMPLE")
        frame = frame.rename(
            columns={
                "vessel_id": "Vessel",
                "name": "Tank",
                "volume_l": "ROB (L)",
                "capacity_l": "Capacity (L)",
                "blend_pct": "Recorded fuel (B%)",
                "age_days": "Effective fuel age (days)",
                "last_bhi": "Last BHI",
            }
        )
    dataframe_or_message(frame[["Vessel", "Tank", "ROB (L)", "Capacity (L)", "Recorded fuel (B%)", "Effective fuel age (days)", "Last BHI", "Condition status"]])

    st.markdown("### Latest bunkering activity")
    bunk = pd.DataFrame(
        rows(cn, "SELECT vessel_id AS Vessel, created_at AS Recorded, bdn_ref AS BDN, delivered_l AS Delivered_L, resulting_age AS Effective_age_days FROM bunkerings ORDER BY id DESC LIMIT 12")
    )
    dataframe_or_message(bunk, "No bunkering transactions recorded yet.")

elif page == "1 · Pre-bunkering":
    st.subheader("Step 1 — Pre-bunkering")
    st.markdown(
        """
<div class="soft-box">
<b>Purpose:</b> identify the vessel and tank, confirm the current fuel inventory, and prepare for the incoming fuel review.
</div>
""",
        unsafe_allow_html=True,
    )
    vessel_id, t = pick_vessel_and_tank("pre")
    show_tank_snapshot(vessel_id, t)

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("#### Suggested pre-bunkering checks")
        st.checkbox("Correct vessel and receiving tank identified", value=True, disabled=True)
        st.checkbox("Recorded ROB reconciled with latest onboard record", value=True, disabled=True)
        st.checkbox("No confidential real data entered into this public demo", value=True, disabled=True)
    with right:
        st.markdown("#### What happens next")
        st.info(
            "Go to **Step 2 — Incoming fuel review** to record the planned delivery, COQ reference, incoming fuel grade, and reviewer confirmation."
        )

    history = pd.DataFrame(
        rows(
            cn,
            "SELECT id AS Review_ID, created_at AS Created, incoming_blend AS Incoming_B_Grade, planned_l AS Planned_L, coq_ref AS COQ, review_status AS Status FROM checks WHERE tank_id=? ORDER BY id DESC LIMIT 10",
            (t["id"],),
        )
    )
    st.markdown("#### Recent review records for this tank")
    dataframe_or_message(history, "No pre-bunkering review records yet.")

elif page == "2 · Incoming fuel review":
    st.subheader("Step 2 — Incoming fuel review")
    st.markdown(
        """
<div class="soft-box">
<b>Purpose:</b> document the planned delivery and confirm that the incoming fuel has been checked against the vessel's recorded approval and supplier documentation.
</div>
""",
        unsafe_allow_html=True,
    )
    vessel_id, t = pick_vessel_and_tank("review")
    show_tank_snapshot(vessel_id, t)

    with st.form("incoming_review"):
        c1, c2 = st.columns(2)
        incoming = c1.selectbox("Incoming fuel grade (B%)", [0, 20, 30, 50, 100], index=3)
        planned = c2.number_input("Planned delivery (L)", min_value=1.0, value=1000.0, step=50.0)
        expected_tank = t["volume_l"] + planned
        fill_pct = min(100.0, 100.0 * expected_tank / t["capacity_l"])
        st.progress(fill_pct / 100.0, text=f"Expected tank quantity after delivery: {expected_tank:,.0f} L / {t['capacity_l']:,.0f} L")

        coq = st.text_input("Supplier COQ reference")
        review_col1, review_col2 = st.columns(2)
        approved = review_col1.checkbox("Incoming fuel grade is within the vessel's recorded approval")
        coq_checked = review_col2.checkbox("COQ has been reviewed")
        no_concern = st.checkbox("No unresolved incoming-fuel concern noted for this review")
        approval_ref = st.text_input("Evidence / review reference")
        reviewer = st.text_input("Reviewer name / ID")
        notes = st.text_area("Review comments", placeholder="Example: Synthetic test entry only. No abnormal concern noted.")
        submitted = st.form_submit_button("Save review")

    if submitted:
        try:
            review_ok = bool(coq_checked and no_concern)
            review_id, status = record_check(
                cn,
                vessel=vessel_id,
                tank_id=t["id"],
                incoming_blend=incoming,
                planned_l=planned,
                coq_ref=coq,
                approved=approved,
                compatible=review_ok,
                approval_ref=approval_ref,
                reviewer=reviewer,
                notes=notes,
            )
            if status == "Reviewed":
                st.success(f"Review #{review_id} saved as REVIEWED. You can now move to Step 3 — Bunkering record.")
            else:
                st.warning(
                    f"Review #{review_id} saved as PENDING. Complete all required checks and references before recording bunkering."
                )
        except ValueError as ex:
            st.error(str(ex))

    recent = pd.DataFrame(
        rows(
            cn,
            "SELECT id AS Review_ID, created_at AS Created, incoming_blend AS Incoming_B_Grade, planned_l AS Planned_L, coq_ref AS COQ, review_status AS Status FROM checks WHERE tank_id=? ORDER BY id DESC LIMIT 10",
            (t["id"],),
        )
    )
    st.markdown("#### Recent review records")
    dataframe_or_message(recent, "No reviews yet.")

elif page == "3 · Bunkering record":
    st.subheader("Step 3 — Bunkering record")
    st.markdown(
        """
<div class="soft-box">
<b>Purpose:</b> record the completed bunkering event using a previously reviewed incoming-fuel record. This updates tank quantity and effective fuel age.
</div>
""",
        unsafe_allow_html=True,
    )
    vessel_id, t = pick_vessel_and_tank("bunk")
    show_tank_snapshot(vessel_id, t)

    checks = rows(
        cn,
        "SELECT * FROM checks WHERE tank_id=? AND review_status='Reviewed' AND NOT EXISTS (SELECT 1 FROM bunkerings b WHERE b.notes LIKE '%[check:' || checks.id || ']%') ORDER BY id DESC",
        (t["id"],),
    )
    if not checks:
        st.warning("No unused reviewed incoming-fuel records were found for this tank. Complete Step 2 first.")
    else:
        check_id = st.selectbox(
            "Reviewed incoming-fuel record",
            [r["id"] for r in checks],
            format_func=lambda x: next(
                f"Review #{r['id']} · COQ {r['coq_ref']} · {r['planned_l']:,.0f} L planned" for r in checks if r["id"] == x
            ),
        )
        selected = next(r for r in checks if r["id"] == check_id)
        st.caption(
            f"Selected incoming fuel: B{selected['incoming_blend']:.0f} · Planned delivery: {selected['planned_l']:,.0f} L · COQ: {selected['coq_ref']}"
        )
        with st.form("bunkering_form"):
            c1, c2, c3 = st.columns(3)
            rob = c1.number_input("Verified ROB before transfer (L)", min_value=0.0, value=float(t["volume_l"]))
            qty = c2.number_input("Actual delivered volume (L)", min_value=0.01, value=float(selected["planned_l"]))
            elapsed = c3.number_input(
                "Elapsed days since last age update",
                min_value=0.0,
                value=0.0,
                help="Use 0 if the recorded age is already current.",
            )
            supplier = st.text_input("Supplier")
            bdn = st.text_input("Bunker delivery note (BDN) reference")
            sample_ref = st.text_input("Representative sample / seal reference")
            notes = st.text_area("Operational observations")
            posted = st.form_submit_button("Save bunkering record")
        if posted:
            try:
                record_id, blend, age = record_bunkering(
                    cn,
                    check_id=check_id,
                    actual_rob=rob,
                    actual_delivered=qty,
                    elapsed_days=elapsed,
                    bdn_ref=bdn,
                    sample_ref=sample_ref,
                    supplier=supplier,
                    notes=notes,
                )
                st.success(
                    f"Bunkering record #{record_id} saved. Tank quantity updated and effective fuel age recalculated to {age:.3f} days."
                )
                st.caption(
                    f"Recorded fuel blend was updated internally for fleet traceability (estimated B{blend:.2f}). The app does not treat this as a compatibility certificate."
                )
                st.rerun()
            except ValueError as ex:
                st.error(str(ex))

    history = pd.DataFrame(
        rows(
            cn,
            "SELECT id AS Record_ID, created_at AS Recorded, bdn_ref AS BDN, delivered_l AS Delivered_L, rob_l AS ROB_Before, resulting_age AS Effective_Age_Days FROM bunkerings WHERE tank_id=? ORDER BY id DESC LIMIT 12",
            (t["id"],),
        )
    )
    st.markdown("#### Bunkering history for this tank")
    dataframe_or_message(history, "No bunkering records yet.")

elif page == "4 · Tank sample & BHI":
    st.subheader("Step 4 — Tank sample and BHI")
    st.markdown(
        """
<div class="soft-box">
<b>Purpose:</b> enter representative tank-sample measurements and calculate a provisional BHI.
The BHI is a screening score only and does not certify fuel suitability.
</div>
""",
        unsafe_allow_html=True,
    )
    vessel_id, t = pick_vessel_and_tank("sample")
    show_tank_snapshot(vessel_id, t)
    st.warning("Enter a representative tank sample result here. Do not simply copy incoming COQ values into the tank-sample form.")

    with st.form("sample_form"):
        c1, c2 = st.columns(2)
        ref = c1.text_input("Tank sample reference")
        lab = c2.text_input("Laboratory / authorised measurement provider")
        c3, c4 = st.columns(2)
        taken = c3.date_input("Sample date", value=date.today())
        method = c4.text_input("Test method / report reference")
        m1, m2, m3 = st.columns(3)
        water = m1.number_input("Water (mg/kg)", min_value=0.0, value=300.0)
        tan = m2.number_input("TAN (mg KOH/g)", min_value=0.0, value=0.30, format="%.3f")
        oxidation = m3.number_input("Oxidation stability (h)", min_value=0.01, value=10.0)
        notes = st.text_area("Remarks / limitations")
        submitted = st.form_submit_button("Save sample and calculate BHI")

    if submitted:
        try:
            sample_id, result = record_sample(
                cn,
                vessel=vessel_id,
                tank_id=t["id"],
                taken_at=taken.isoformat(),
                ref=ref,
                laboratory=lab,
                method_ref=method,
                water=water,
                tan=tan,
                oxidation=oxidation,
                limits=limits,
                weights=weights,
                notes=notes,
            )
            mc1, mc2 = st.columns(2)
            mc1.metric("Provisional BHI", f"{result['score']:.1f} / 100")
            mc2.metric("Screening status", result["status"])
            if result["breaches"]:
                st.error("Reference limit breach: " + ", ".join(result["breaches"]) + ". Escalate for qualified review.")
            else:
                st.info("No illustrative reference-limit breach detected. Continue to fleet review and alert management as required.")
            st.success(f"Sample result #{sample_id} saved.")
        except ValueError as ex:
            st.error(str(ex))

    history = pd.DataFrame(
        rows(
            cn,
            "SELECT taken_at AS Sampled, sample_ref AS Sample, laboratory AS Laboratory, water AS Water_mgkg, tan AS TAN, oxidation AS Oxidation_h, bhi AS BHI, status AS Status FROM samples WHERE tank_id=? ORDER BY id DESC",
            (t["id"],),
        )
    )
    st.markdown("#### Tank-sample history")
    dataframe_or_message(history, "No tank-sample results yet.")
    if len(history) > 1:
        chart = history.iloc[::-1].copy().set_index("Sampled")
        st.line_chart(chart["BHI"])

elif page == "5 · Alerts & exports":
    st.subheader("Step 5 — Alerts and Power BI exports")
    st.markdown(
        """
<div class="soft-box">
<b>Purpose:</b> review open items, document actions taken, and export synthetic datasets for Power BI.
</div>
""",
        unsafe_allow_html=True,
    )
    alerts = pd.DataFrame(rows(cn, "SELECT * FROM alerts ORDER BY id DESC"))
    dataframe_or_message(alerts, "No alerts recorded yet.")

    open_alerts = [a for a in rows(cn, "SELECT * FROM alerts WHERE status!='Closed' ORDER BY id DESC")]
    if open_alerts:
        st.markdown("#### Update an alert")
        with st.form("alert_update"):
            aid = st.selectbox(
                "Alert",
                [a["id"] for a in open_alerts],
                format_func=lambda x: f"#{x} · " + next(a["details"][:90] for a in open_alerts if a["id"] == x),
            )
            s1, s2 = st.columns(2)
            status = s1.selectbox("Workflow status", ["Open", "Under review", "Closed"])
            owner = s2.text_input("Responsible reviewer")
            action = st.text_area("Investigation / action taken")
            submit_alert = st.form_submit_button("Save alert update")
        if submit_alert:
            try:
                update_alert(cn, aid, status, owner, action)
                st.success("Alert updated.")
                st.rerun()
            except ValueError as ex:
                st.error(str(ex))

    st.markdown("#### Export synthetic datasets")
    st.caption("Use these CSVs in Microsoft Power BI Desktop for fleet reporting and dashboards.")
    for entity in ("vessels", "tanks", "checks", "bunkerings", "samples", "alerts"):
        dat = pd.DataFrame(rows(cn, f"SELECT * FROM {entity}"))
        st.download_button(
            f"Download {entity}.csv",
            dat.to_csv(index=False).encode(),
            file_name=f"{entity}.csv",
            mime="text/csv",
            key=f"csv_{entity}",
        )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for entity in ("vessels", "tanks", "checks", "bunkerings", "samples", "alerts"):
            dat = pd.DataFrame(rows(cn, f"SELECT * FROM {entity}"))
            zf.writestr(f"{entity}.csv", dat.to_csv(index=False))
    st.download_button(
        "Download all CSVs (ZIP)",
        archive.getvalue(),
        file_name="fleet_powerbi_exports.zip",
        mime="application/zip",
    )

elif page == "6 · Scientific basis":
    st.subheader("Step 6 — Scientific basis")
    st.markdown(
        """
<div class="soft-box">
<b>Purpose:</b> show how the provisional BHI weights are generated and how the screening score changes under different weighting schemes.
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown("#### MCDA weighting")
    st.caption("These ratings are provisional and researcher-defined. They are not laboratory calibrated.")
    values = {}
    for param in PARAMETERS:
        st.markdown(f"**{param}**")
        cols = st.columns(4)
        values[param] = tuple(
            cols[j].slider(f"{CRITERIA[j]} — {param}", 1, 5, int(DEFAULT_MCDA[param][j]), key=f"{param}_{j}")
            for j in range(4)
        )
    new_weights = mcda_weights(values)
    weights_df = pd.DataFrame(
        [{"Parameter": p, "Calculated weight (%)": round(new_weights[p], 3)} for p in PARAMETERS]
    )
    st.dataframe(weights_df, use_container_width=True, hide_index=True)
    st.bar_chart(pd.DataFrame({"Parameter": list(new_weights), "Weight": list(new_weights.values())}).set_index("Parameter"))

    st.markdown("#### FMEA summary")
    fmea = pd.DataFrame(FMEA, columns=["ID", "Parameter", "Failure mode", "Severity", "Occurrence", "Detection difficulty"])
    fmea["RPN"] = fmea["Severity"] * fmea["Occurrence"] * fmea["Detection difficulty"]
    st.dataframe(fmea, use_container_width=True, hide_index=True)

    st.markdown("#### Weight sensitivity example")
    s1, s2, s3 = st.columns(3)
    water = s1.number_input("Water measurement", value=300.0, min_value=0.0)
    tan = s2.number_input("TAN measurement", value=0.30, min_value=0.0)
    oxidation = s3.number_input("Oxidation measurement", value=10.0, min_value=0.01)
    schemes = {
        "Editable MCDA": new_weights,
        "Equal thirds": {p: 100 / 3 for p in PARAMETERS},
        "Former 35/35/30": dict(zip(PARAMETERS, [35, 35, 30])),
        "Exploratory FMEA": dict(zip(PARAMETERS, [31.8, 25.2, 43])),
    }
    sens = pd.DataFrame(
        [
            {"Scheme": name, "Provisional BHI": round(calculate_bhi(water, tan, oxidation, limits, wt)["score"], 2)}
            for name, wt in schemes.items()
        ]
    )
    st.dataframe(sens, hide_index=True, use_container_width=True)
    st.info(
        "Validation scope here is limited to deterministic formulas, workflow logic and sensitivity checks. "
        "It does not prove chemical compatibility, fuel-grade conformity or real-world deterioration behaviour."
    )

st.divider()
st.caption("Academic research demonstrator — not affiliated with or deployed by PSA Marine. Enter synthetic data only.")
