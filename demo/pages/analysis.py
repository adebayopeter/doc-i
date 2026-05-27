import streamlit as st

from api_client import api_get
from constants import DECISION_COLOUR


def render():
    st.title("🔍 Analysis")
    st.caption(
        "Unified record, validation results, and routing decision "
        "for a submission."
    )

    # ── Submission selector ────────────────────────────────────────────
    sub_result = api_get("/v1/submissions")
    submissions = sub_result.get("data", {}).get("items", [])

    if not submissions:
        st.warning("No submissions found.")
        st.stop()

    sub_options = {
        f"{s.get('reference') or s['submission_id'][:12]} "
        f"({s['process_name']}) [{s['status']}]": s["submission_id"]
        for s in submissions
    }

    default_idx = 0
    if st.session_state.selected_submission_id:
        for i, sid in enumerate(sub_options.values()):
            if sid == st.session_state.selected_submission_id:
                default_idx = i
                break

    selected_label = st.selectbox(
        "Select Submission",
        options=list(sub_options.keys()),
        index=default_idx,
    )
    selected_sid = sub_options[selected_label]

    # ── Tabs ───────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["📊 Unified Record", "✅ Validation", "🎯 Decision"])

    # ── Tab 1: Unified Record ──────────────────────────────────────────
    with tab1:
        _render_unified_record(selected_sid)

    # ── Tab 2: Validation ──────────────────────────────────────────────
    with tab2:
        _render_validation(selected_sid)

    # ── Tab 3: Decision ────────────────────────────────────────────────
    with tab3:
        _render_decision(selected_sid)


def _render_unified_record(sid: str):
    result = api_get(f"/v1/analysis/submissions/{sid}/record")
    if not result.get("success"):
        st.error(result.get("message"))
        return

    data = result["data"]
    col1, col2, col3 = st.columns(3)
    col1.metric("Classified Documents", data.get("classified_document_count", 0))
    col2.metric("Fields Extracted", data.get("field_count", 0))
    conflicts = sum(
        1
        for f in data.get("fields", {}).values()
        if f.get("hasConflict")
    )
    col3.metric("Conflicts Detected", conflicts)

    st.divider()

    fields = data.get("fields", {})
    if not fields:
        st.info("No classified documents yet — upload and classify documents first.")
        return

    for field_name, fdata in fields.items():
        conflict_icon = "⚠️" if fdata.get("hasConflict") else "✅"
        null_icon = "❌" if fdata.get("isNull") else ""

        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 3, 2])
            with col1:
                st.markdown(f"{conflict_icon} {null_icon} **{field_name}**")
                st.caption(f"Source: {fdata.get('sourceDocType', '—')}")
            with col2:
                value = fdata.get("bestValue") or "*(not found)*"
                st.markdown(f"**{value}**")
            with col3:
                conf = fdata.get("bestConfidence", 0)
                st.progress(conf / 100, text=f"{conf:.0f}%")

            if fdata.get("hasConflict"):
                all_vals = fdata.get("allValues", [])
                conflict_str = " vs ".join(
                    f"`{v['value']}`"
                    for v in all_vals
                    if v.get("value")
                )
                st.warning(f"⚠️ Conflict across documents: {conflict_str}")


def _render_validation(sid: str):
    result = api_get(f"/v1/analysis/submissions/{sid}/validation")
    if not result.get("success"):
        st.error(result.get("message"))
        return

    data = result["data"]
    summary = data.get("summary", {})

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Passed", summary.get("pass", 0))
    col2.metric("Failed", summary.get("fail", 0))
    col3.metric("Warned", summary.get("warn", 0))
    col4.metric("Skipped", summary.get("skip", 0))

    st.divider()

    results = data.get("results", [])
    if not results:
        st.info("No validation rules to run.")
        return

    for rule in results:
        status = rule.get("status")
        severity = rule.get("severity")
        icon = (
            "✅" if status == "pass"
            else "❌" if status == "fail"
            else "⚠️" if status == "warn"
            else "⏭️"
        )

        colour_fn = (
            st.success if status == "pass"
            else st.error if status == "fail" and severity == "error"
            else st.warning if status in {"fail", "warn"}
            else st.info
        )

        colour_fn(
            f"{icon} **{rule.get('name')}** "
            f"[{rule.get('type')}] — {rule.get('message')}"
        )


def _render_decision(sid: str):
    result = api_get(f"/v1/analysis/submissions/{sid}/decision")
    if not result.get("success"):
        st.error(result.get("message"))
        return

    data = result["data"]
    overall = data.get("overallDecision", "auto")
    reason = data.get("reason", "")
    summary = data.get("summary", {})
    thresholds = data.get("thresholds", {})

    # Overall verdict
    decision_colour = DECISION_COLOUR.get(overall, "⚪")
    if overall == "auto":
        st.success(f"{decision_colour} **DECISION: AUTO-PROCESS** — {reason}")
    elif overall == "review":
        st.warning(f"{decision_colour} **DECISION: REVIEW REQUIRED** — {reason}")
    else:
        st.error(f"{decision_colour} **DECISION: MANUAL INPUT** — {reason}")

    st.divider()

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "🟢 Auto-Process",
        summary.get("auto", 0),
        help=f"Confidence ≥ {thresholds.get('autoAbove', 85)}%",
    )
    col2.metric(
        "🟡 Review",
        summary.get("review", 0),
        help="Confidence in the middle range",
    )
    col3.metric(
        "🔴 Manual Input",
        summary.get("manual", 0),
        help=f"Confidence < {thresholds.get('manualBelow', 60)}%",
    )

    st.caption(
        f"Thresholds: auto ≥ {thresholds.get('autoAbove', 85)}% · "
        f"manual < {thresholds.get('manualBelow', 60)}%"
    )

    st.divider()
    st.subheader("Field-by-Field Decisions")

    field_decisions = data.get("fieldDecisions", [])
    if not field_decisions:
        st.info("No fields to evaluate.")
        return
    for fd in field_decisions:
        d = fd.get("decision")
        icon = DECISION_COLOUR.get(d, "⚪")
        conflict = " ⚠️ conflict" if fd.get("hasConflict") else ""
        missing = " ❌ missing" if fd.get("isMissing") else ""
        conf = fd.get("confidence", 0)

        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 3, 2])
            with col1:
                st.markdown(
                    f"{icon} **{fd.get('field')}**"
                    f"{conflict}{missing}"
                )
            with col2:
                val = fd.get("value") or "*(not found)*"
                st.caption(val)
            with col3:
                st.progress(
                    conf / 100,
                    text=f"{conf:.0f}% — {d}",
                )
