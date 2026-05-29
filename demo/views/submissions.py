import streamlit as st

from api_client import api_get, api_post
from constants import API_BASE, HEADERS, STATUS_COLOUR


def render():
    st.title("📋 Submissions")
    st.caption(
        "Open a case for an applicant under a process. "
        "Upload documents against the submission."
    )

    # ── Process selector ───────────────────────────────────────────────
    proc_result = api_get("/v1/processes")
    processes = proc_result.get("data", {}).get("items", [])

    if not processes:
        st.warning("No active processes. Create one on the Processes page first.")
        st.stop()

    proc_options = {p["name"]: p["process_id"] for p in processes}
    selected_name = st.selectbox(
        "Select Process",
        options=list(proc_options.keys()),
        index=0,
    )
    selected_pid = proc_options[selected_name]

    # ── Create submission ──────────────────────────────────────────────
    with st.expander("➕ Open New Submission", expanded=False):
        with st.form("create_submission"):
            col1, col2 = st.columns(2)
            with col1:
                reference = st.text_input(
                    "Case Reference",
                    placeholder="e.g. APP-2025-001",
                )
            with col2:
                applicant_id = st.text_input(
                    "Applicant ID",
                    placeholder="e.g. usr_emeka_obi",
                )

            submitted = st.form_submit_button(
                "Open Submission", type="primary", use_container_width=True
            )

        if submitted:
            result = api_post(
                "/v1/submissions",
                json={
                    "process_id": selected_pid,
                    "reference": reference or None,
                    "applicant_id": applicant_id or None,
                },
            )
            if result.get("success"):
                sid = result["data"]["submission_id"]
                st.success(f"✅ Submission opened: `{sid}`")
                st.session_state.selected_submission_id = sid
                st.rerun()
            else:
                st.error(
                    f"❌ {result.get('message', 'Failed to open submission')}"
                )

    st.divider()

    # ── List submissions ───────────────────────────────────────────────
    sub_result = api_get(f"/v1/submissions?process_id={selected_pid}")
    if not sub_result.get("success"):
        st.error(f"Could not load submissions: {sub_result.get('message')}")
        return

    submissions = sub_result.get("data", {}).get("items", [])
    total = sub_result.get("data", {}).get("total", 0)

    st.subheader(f"Submissions under **{selected_name}** ({total})")

    if total == 0:
        st.info("No submissions yet for this process.")
        return

    for sub in submissions:
        colour = STATUS_COLOUR.get(sub["status"], "⚪")
        progress = sub.get("progress", {})
        classified = progress.get("classified", 0)
        required = progress.get("required", 0)
        pct = int((classified / required * 100) if required > 0 else 0)
        sub_status = sub["status"]

        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([4, 2, 2, 2, 2])
            with col1:
                ref = sub.get("reference") or "—"
                applicant = sub.get("applicant_id") or "—"
                st.markdown(f"**{ref}** · {applicant}")
                st.caption(f"`{sub['submission_id']}`")
                st.progress(
                    pct / 100,
                    text=f"{classified}/{required} docs classified",
                )
            with col2:
                st.markdown(f"{colour} **{sub_status.upper()}**")
                st.caption(
                    sub["created_at"][:10]
                    if sub.get("created_at")
                    else ""
                )
            with col3:
                if sub_status not in {"complete", "rejected"}:
                    if st.button(
                            "Upload Docs",
                            key=f"upload_{sub['submission_id']}",
                            use_container_width=True,
                    ):
                        st.session_state.selected_submission_id = sub[
                            "submission_id"
                        ]
                        st.session_state.active_page = "Documents"
                        st.rerun()
            with col4:
                if st.button(
                        "Analyse",
                        key=f"analyse_{sub['submission_id']}",
                        use_container_width=True,
                ):
                    st.session_state.selected_submission_id = sub[
                        "submission_id"
                    ]
                    st.session_state.active_page = "Analysis"
                    st.rerun()
            with col5:
                if sub_status == "in_progress":
                    if st.button(
                            "✅ Complete",
                            key=f"complete_{sub['submission_id']}",
                            use_container_width=True,
                    ):
                        st.session_state[
                            f"confirm_complete_{sub['submission_id']}"
                        ] = True
                        st.rerun()
                elif sub_status == "complete":
                    st.caption("✅ Completed")
                elif sub_status == "rejected":
                    st.caption("🔴 Rejected")

        # ── Complete confirmation ──────────────────────────────────────
        if st.session_state.get(f"confirm_complete_{sub['submission_id']}"):
            st.warning(
                f"⚠️ Mark **{sub.get('reference') or sub['submission_id'][:12]}** "
                f"as complete? This cannot be undone — no further documents "
                f"can be uploaded after this."
            )
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button(
                        "Yes, mark complete",
                        key=f"confirm_complete_yes_{sub['submission_id']}",
                        type="primary",
                        use_container_width=True,
                ):
                    import requests as req

                    resp = req.patch(
                        f"{API_BASE}/v1/submissions/{sub['submission_id']}/status",
                        headers=HEADERS,
                        json={"status": "complete"},
                        timeout=10,
                    )
                    result = resp.json()
                    st.session_state[
                        f"confirm_complete_{sub['submission_id']}"
                    ] = False
                    if result.get("success"):
                        st.success("✅ Submission marked as complete.")
                    else:
                        st.error(
                            f"❌ {result.get('message', 'Failed')}"
                        )
                    st.rerun()
            with col_no:
                if st.button(
                        "Cancel",
                        key=f"confirm_complete_no_{sub['submission_id']}",
                        use_container_width=True,
                ):
                    st.session_state[
                        f"confirm_complete_{sub['submission_id']}"
                    ] = False
                    st.rerun()
