"""
Doc-I — Document Intelligence Platform
Streamlit Demo Application

Demonstrates the full document processing pipeline:
  1. Create a process with a document checklist
  2. Open a submission for an applicant
  3. Upload documents — triggers AI classification
  4. View extracted fields and confidence scores
  5. Run validation and see the routing decision
"""

import os
import time

import requests
import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Doc-I — Document Intelligence",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── API config ─────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE_URL", "http://api:8012")
API_KEY = os.getenv("SECRET_KEY", "dev-secret-change-this-before-production")

HEADERS = {
    "X-API-Key": API_KEY,
    "Accept": "application/json",
}


# ── API helpers ────────────────────────────────────────────────────────────
def api_get(path: str) -> dict:
    """GET request to the API — returns parsed JSON."""
    try:
        response = requests.get(f"{API_BASE}{path}", headers=HEADERS, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def api_post(path: str, json: dict = None, files: dict = None) -> dict:
    """POST request — handles both JSON and multipart."""
    try:
        headers = {k: v for k, v in HEADERS.items() if k != "Content-Type"}
        if files:
            response = requests.post(
                f"{API_BASE}{path}",
                headers=headers,
                files=files,
                timeout=30,
            )
        else:
            response = requests.post(
                f"{API_BASE}{path}",
                headers=headers,
                json=json,
                timeout=10,
            )
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def api_patch(path: str, params: dict = None) -> dict:
    """PATCH request."""
    try:
        response = requests.patch(
            f"{API_BASE}{path}",
            headers=HEADERS,
            params=params,
            timeout=10,
        )
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def api_delete(path: str) -> dict:
    """DELETE request."""
    try:
        response = requests.delete(
            f"{API_BASE}{path}", headers=HEADERS, timeout=10
        )
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def check_api_health() -> bool:
    """Returns True if the API is reachable."""
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


# ── Colours ────────────────────────────────────────────────────────────────
DECISION_COLOUR = {
    "auto": "🟢",
    "review": "🟡",
    "manual": "🔴",
}

STATUS_COLOUR = {
    "open": "⚪",
    "in_progress": "🔵",
    "complete": "🟢",
    "rejected": "🔴",
    "uploaded": "⚪",
    "processing": "🔵",
    "classified": "🟢",
    "failed": "🔴",
}

# ── Session state defaults ─────────────────────────────────────────────────
defaults = {
    "selected_process_id": None,
    "selected_submission_id": None,
    "active_page": "Processes",
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://img.icons8.com/fluency/96/document.png",
        width=60,
    )
    st.title("Doc-I Platform")
    st.caption("Document Intelligence Demo")

    st.divider()

    # API health check
    if check_api_health():
        st.success("✅ API connected")
    else:
        st.error("❌ API unreachable")
        st.caption(f"Trying: {API_BASE}")
        st.stop()

    st.divider()

    page = st.radio(
        "Navigate",
        ["🏠 Processes", "📋 Submissions", "📄 Documents", "🔍 Analysis", "⚙️ Config"],
        index=["🏠 Processes", "📋 Submissions", "📄 Documents", "🔍 Analysis", "⚙️ Config"].index(
            f"{'🏠' if st.session_state.active_page == 'Processes' else '📋' if st.session_state.active_page == 'Submissions' else '📄' if st.session_state.active_page == 'Documents' else '🔍' if st.session_state.active_page == 'Analysis' else '⚙️'} {st.session_state.active_page}"
        ),
        label_visibility="collapsed",
    )

    page_name = page.split(" ", 1)[1]
    st.session_state.active_page = page_name

    st.divider()
    st.caption(f"API: `{API_BASE}`")


# ══════════════════════════════════════════════════════════════════════
# PAGE: PROCESSES
# ══════════════════════════════════════════════════════════════════════
if page_name == "Processes":
    st.title("📁 Processes")
    st.caption(
        "Define document workflows. Each process specifies which documents "
        "are required — the AI uses this checklist to classify uploads."
    )

    # ── Create new process ─────────────────────────────────────────────
    with st.expander("➕ Create New Process", expanded=False):
        with st.form("create_process"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input(
                    "Process Name *",
                    placeholder="e.g. RSA Mortgage",
                )
                description = st.text_area(
                    "Description",
                    placeholder="What this process is for",
                    height=80,
                )
            with col2:
                color_var = st.selectbox(
                    "Colour",
                    ["info", "success", "warning", "danger"],
                )
                icon = st.text_input(
                    "Icon",
                    value="ti-file",
                    placeholder="Tabler icon name",
                )

            st.subheader("Document Checklist")
            st.caption("Add the documents required for this process (minimum 1).")

            num_docs = st.number_input(
                "Number of documents", min_value=1, max_value=20, value=3
            )

            doc_rows = []
            for i in range(int(num_docs)):
                c1, c2, c3 = st.columns([4, 3, 2])
                with c1:
                    doc_name = st.text_input(
                        f"Document {i + 1} name",
                        key=f"doc_name_{i}",
                        placeholder="e.g. National ID / NIN slip",
                    )
                with c2:
                    doc_cat = st.text_input(
                        f"Category",
                        key=f"doc_cat_{i}",
                        placeholder="e.g. Identity",
                    )
                with c3:
                    doc_req = st.checkbox(
                        "Required",
                        key=f"doc_req_{i}",
                        value=True,
                    )
                if doc_name and doc_cat:
                    doc_rows.append(
                        {
                            "name": doc_name,
                            "category": doc_cat,
                            "is_required": doc_req,
                        }
                    )

            submitted = st.form_submit_button(
                "Create Process", type="primary", use_container_width=True
            )

        if submitted:
            if not name:
                st.error("Process name is required.")
            elif len(doc_rows) == 0:
                st.error("At least one complete document is required.")
            else:
                result = api_post(
                    "/v1/processes",
                    json={
                        "name": name,
                        "description": description,
                        "color_var": color_var,
                        "icon": icon,
                        "documents": doc_rows,
                    },
                )
                if result.get("success"):
                    st.success(
                        f"✅ Process created: **{name}** "
                        f"(ID: `{result['data']['process_id']}`)"
                    )
                    st.rerun()
                else:
                    st.error(f"❌ {result.get('message', 'Failed to create process')}")

    st.divider()


# ── List processes ─────────────────────────────────────────────────
    result = api_get("/v1/processes")
    if not result.get("success"):
        st.error(f"Could not load processes: {result.get('message')}")
    else:
        data = result.get("data", {})
        processes = data.get("items", [])
        total = data.get("total", 0)

        st.subheader(f"All Processes ({total})")

        if total == 0:
            st.info(
                "No processes yet. Create one above to get started."
            )
        else:
            for proc in processes:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([5, 2, 2])
                    with col1:
                        st.markdown(f"**{proc['name']}**")
                        if proc.get("description"):
                            st.caption(proc["description"])
                        st.caption(
                            f"`{proc['process_id']}` · "
                            f"{proc['document_count']} documents"
                        )
                    with col2:
                        if st.button(
                            "Open",
                            key=f"open_{proc['process_id']}",
                            use_container_width=True,
                        ):
                            st.session_state.selected_process_id = proc[
                                "process_id"
                            ]
                            st.session_state.active_page = "Submissions"
                            st.rerun()
                    with col3:
                        if st.button(
                            "🗑️ Deactivate",
                            key=f"del_{proc['process_id']}",
                            use_container_width=True,
                        ):
                            api_delete(f"/v1/processes/{proc['process_id']}")
                            st.rerun()

# ══════════════════════════════════════════════════════════════════════
# PAGE: SUBMISSIONS
# ══════════════════════════════════════════════════════════════════════
elif page_name == "Submissions":
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
    else:
        submissions = sub_result.get("data", {}).get("items", [])
        total = sub_result.get("data", {}).get("total", 0)

        st.subheader(f"Submissions under **{selected_name}** ({total})")

        if total == 0:
            st.info("No submissions yet for this process.")
        else:
            for sub in submissions:
                colour = STATUS_COLOUR.get(sub["status"], "⚪")
                progress = sub.get("progress", {})
                classified = progress.get("classified", 0)
                required = progress.get("required", 0)
                pct = int((classified / required * 100) if required > 0 else 0)

                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
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
                        st.markdown(f"{colour} **{sub['status'].upper()}**")
                        st.caption(
                            sub["created_at"][:10]
                            if sub.get("created_at")
                            else ""
                        )
                    with col3:
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


# ══════════════════════════════════════════════════════════════════════
# PAGE: DOCUMENTS
# ══════════════════════════════════════════════════════════════════════
elif page_name == "Documents":
    st.title("📄 Documents")
    st.caption(
        "Upload documents to a submission. "
        "Classification runs automatically in the background."
    )

    # ── Submission selector ────────────────────────────────────────────
    sub_result = api_get("/v1/submissions")
    submissions = sub_result.get("data", {}).get("items", [])

    if not submissions:
        st.warning(
            "No submissions found. Create one on the Submissions page first."
        )
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

    # ── Upload ─────────────────────────────────────────────────────────
    sub_detail = api_get(f"/v1/submissions/{selected_sid}")
    sub_data = sub_detail.get("data", {})
    status = sub_data.get("status", "open")

    if status in {"complete", "rejected"}:
        st.warning(
            f"This submission is **{status}** — no more documents can be uploaded."
        )
    else:
        uploaded_file = st.file_uploader(
            "Upload a document",
            type=["pdf", "png", "jpg", "jpeg", "webp", "tiff"],
            help="PDF, PNG, JPG, WEBP or TIFF — max 20MB",
        )

        if uploaded_file:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(
                    f"**{uploaded_file.name}** "
                    f"({uploaded_file.size / 1024:.1f} KB)"
                )
            with col2:
                if st.button(
                    "Upload & Classify",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner("Uploading and queuing classification..."):
                        result = api_post(
                            f"/v1/documents/submissions/{selected_sid}/upload",
                            files={
                                "file": (
                                    uploaded_file.name,
                                    uploaded_file.getvalue(),
                                    uploaded_file.type,
                                )
                            },
                        )
                    if result.get("success"):
                        st.success(
                            f"✅ Uploaded: `{result['data']['document_id']}` — "
                            f"classification running..."
                        )
                        st.rerun()
                    else:
                        st.error(
                            f"❌ {result.get('message', 'Upload failed')}"
                        )

    st.divider()

    # ── Document list ──────────────────────────────────────────────────
    docs_result = api_get(f"/v1/submissions/{selected_sid}/documents")
    if not docs_result.get("success"):
        st.error(f"Could not load documents: {docs_result.get('message')}")
    else:
        docs_data = docs_result.get("data", {})
        documents = docs_data.get("documents", [])
        total = docs_data.get("total", 0)
        classified = docs_data.get("classified", 0)
        processing = docs_data.get("processing", 0)
        failed = docs_data.get("failed", 0)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total", total)
        col2.metric("Classified", classified)
        col3.metric("Processing", processing)
        col4.metric("Failed", failed)

        st.divider()

        if total == 0:
            st.info("No documents uploaded yet.")
        else:
            for doc in documents:
                colour = STATUS_COLOUR.get(doc["status"], "⚪")
                conf = doc.get("overall_confidence")
                conf_str = f"{conf:.0f}%" if conf is not None else "—"

                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns([4, 2, 2, 1])
                    with col1:
                        st.markdown(f"**{doc['filename']}**")
                        if doc.get("document_type"):
                            st.caption(f"📌 {doc['document_type']}")
                        st.caption(f"`{doc['document_id']}`")
                    with col2:
                        st.markdown(f"{colour} {doc['status'].upper()}")
                    with col3:
                        st.markdown(f"Confidence: **{conf_str}**")
                    with col4:
                        if st.button(
                            "View",
                            key=f"view_{doc['document_id']}",
                            use_container_width=True,
                        ):
                            st.session_state[
                                f"show_doc_{doc['document_id']}"
                            ] = True

                # Expanded document detail
                if st.session_state.get(f"show_doc_{doc['document_id']}"):
                    doc_detail = api_get(f"/v1/documents/{doc['document_id']}")
                    detail = doc_detail.get("data", {})

                    with st.expander(
                        f"📋 {detail.get('filename')} — Extracted Fields",
                        expanded=True,
                    ):
                        fields = detail.get("extracted_fields") or {}
                        flags = detail.get("flags") or []
                        summary = detail.get("summary")

                        if summary:
                            st.info(f"💬 {summary}")

                        if flags:
                            for flag in flags:
                                ftype = flag.get("type", "ok")
                                msg = flag.get("message", "")
                                if ftype == "err":
                                    st.error(msg)
                                elif ftype == "warn":
                                    st.warning(msg)
                                else:
                                    st.success(msg)

                        if fields:
                            st.subheader("Extracted Fields")
                            rows = []
                            for field_name, data in fields.items():
                                if isinstance(data, dict):
                                    rows.append(
                                        {
                                            "Field": field_name,
                                            "Value": data.get("value") or "—",
                                            "Confidence": f"{data.get('confidence', 0):.0f}%",
                                        }
                                    )
                            if rows:
                                st.table(rows)
                        elif detail.get("status") == "processing":
                            st.spinner("Classification still running...")
                        elif detail.get("status") == "uploaded":
                            st.info(
                                "Document uploaded — classification will start shortly."
                            )

                        if st.button(
                            "Close",
                            key=f"close_{doc['document_id']}",
                        ):
                            st.session_state[
                                f"show_doc_{doc['document_id']}"
                            ] = False
                            st.rerun()

                        if status not in {"complete", "rejected"}:
                            if st.button(
                                "🗑️ Remove",
                                key=f"del_doc_{doc['document_id']}",
                            ):
                                api_delete(f"/v1/documents/{doc['document_id']}")
                                st.session_state[
                                    f"show_doc_{doc['document_id']}"
                                ] = False
                                st.rerun()


# ══════════════════════════════════════════════════════════════════════
# PAGE: ANALYSIS
# ══════════════════════════════════════════════════════════════════════
elif page_name == "Analysis":
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
        result = api_get(
            f"/v1/analysis/submissions/{selected_sid}/record"
        )
        if not result.get("success"):
            st.error(result.get("message"))
        else:
            data = result["data"]
            col1, col2, col3 = st.columns(3)
            col1.metric(
                "Classified Documents",
                data.get("classified_document_count", 0),
            )
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
                st.info(
                    "No classified documents yet — upload and classify "
                    "documents first."
                )
            else:
                for field_name, fdata in fields.items():
                    conflict_icon = "⚠️" if fdata.get("hasConflict") else "✅"
                    null_icon = "❌" if fdata.get("isNull") else ""

                    with st.container(border=True):
                        col1, col2, col3 = st.columns([3, 3, 2])
                        with col1:
                            st.markdown(
                                f"{conflict_icon} {null_icon} **{field_name}**"
                            )
                            st.caption(
                                f"Source: {fdata.get('sourceDocType', '—')}"
                            )
                        with col2:
                            value = fdata.get("bestValue") or "*(not found)*"
                            st.markdown(f"**{value}**")
                        with col3:
                            conf = fdata.get("bestConfidence", 0)
                            st.progress(
                                conf / 100,
                                text=f"{conf:.0f}%",
                            )

                        if fdata.get("hasConflict"):
                            all_vals = fdata.get("allValues", [])
                            conflict_str = " vs ".join(
                                f"`{v['value']}`"
                                for v in all_vals
                                if v.get("value")
                            )
                            st.warning(
                                f"⚠️ Conflict across documents: {conflict_str}"
                            )

    # ── Tab 2: Validation ──────────────────────────────────────────────
    with tab2:
        result = api_get(
            f"/v1/analysis/submissions/{selected_sid}/validation"
        )
        if not result.get("success"):
            st.error(result.get("message"))
        else:
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
            else:
                for rule in results:
                    status = rule.get("status")
                    severity = rule.get("severity")
                    icon = (
                        "✅"
                        if status == "pass"
                        else "❌"
                        if status == "fail"
                        else "⚠️"
                        if status == "warn"
                        else "⏭️"
                    )

                    colour_fn = (
                        st.success
                        if status == "pass"
                        else st.error
                        if status == "fail" and severity == "error"
                        else st.warning
                        if status in {"fail", "warn"}
                        else st.info
                    )

                    colour_fn(
                        f"{icon} **{rule.get('name')}** "
                        f"[{rule.get('type')}] — {rule.get('message')}"
                    )

    # ── Tab 3: Decision ────────────────────────────────────────────────
    with tab3:
        result = api_get(
            f"/v1/analysis/submissions/{selected_sid}/decision"
        )
        if not result.get("success"):
            st.error(result.get("message"))
        else:
            data = result["data"]
            overall = data.get("overallDecision", "auto")
            reason = data.get("reason", "")
            summary = data.get("summary", {})
            thresholds = data.get("thresholds", {})

            # Overall verdict
            decision_colour = DECISION_COLOUR.get(overall, "⚪")
            if overall == "auto":
                st.success(
                    f"{decision_colour} **DECISION: AUTO-PROCESS** — {reason}"
                )
            elif overall == "review":
                st.warning(
                    f"{decision_colour} **DECISION: REVIEW REQUIRED** — {reason}"
                )
            else:
                st.error(
                    f"{decision_colour} **DECISION: MANUAL INPUT** — {reason}"
                )

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
            else:
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


# ══════════════════════════════════════════════════════════════════════
# PAGE: CONFIG
# ══════════════════════════════════════════════════════════════════════
elif page_name == "Config":
    st.title("⚙️ Configuration")
    st.caption(
        "Manage validation rules and confidence thresholds. "
        "Changes take effect immediately."
    )

    tab1, tab2 = st.tabs(["📏 Validation Rules", "🎚️ Thresholds"])

    # ── Tab 1: Validation rules ────────────────────────────────────────
    with tab1:
        result = api_get("/v1/config/rules")
        if not result.get("success"):
            st.error(result.get("message"))
        else:
            data = result["data"]
            rules = data.get("items", [])
            total = data.get("total", 0)
            enabled = data.get("enabled", 0)
            disabled = data.get("disabled", 0)

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Rules", total)
            col2.metric("Enabled", enabled)
            col3.metric("Disabled", disabled)

            st.divider()

            type_filter = st.selectbox(
                "Filter by type",
                ["All", "required", "format", "logical", "cross_doc"],
            )

            filtered = (
                rules
                if type_filter == "All"
                else [r for r in rules if r["rule_type"] == type_filter]
            )

            for rule in filtered:
                enabled_icon = "✅" if rule["is_enabled"] else "⏸️"
                sev_icon = "🔴" if rule["severity"] == "error" else "🟡"

                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
                    with col1:
                        st.markdown(
                            f"{enabled_icon} **{rule['name']}**"
                        )
                        details = []
                        if rule.get("check"):
                            details.append(f"check: `{rule['check']}`")
                        if rule.get("pattern"):
                            details.append(f"pattern: `{rule['pattern']}`")
                        if details:
                            st.caption(" · ".join(details))
                        st.caption(
                            f"`{rule['id']}` · {sev_icon} {rule['severity']} "
                            f"· {rule['rule_type']}"
                        )
                    with col2:
                        toggle_label = (
                            "Disable" if rule["is_enabled"] else "Enable"
                        )
                        if st.button(
                            toggle_label,
                            key=f"toggle_{rule['id']}",
                            use_container_width=True,
                        ):
                            import requests as req

                            req.patch(
                                f"{API_BASE}/v1/config/rules/{rule['id']}",
                                headers=HEADERS,
                                json={"enabled": not rule["is_enabled"]},
                                timeout=10,
                            )
                            st.rerun()
                    with col3:
                        new_sev = (
                            "warning"
                            if rule["severity"] == "error"
                            else "error"
                        )
                        if st.button(
                            f"→ {new_sev}",
                            key=f"sev_{rule['id']}",
                            use_container_width=True,
                        ):
                            import requests as req

                            req.patch(
                                f"{API_BASE}/v1/config/rules/{rule['id']}",
                                headers=HEADERS,
                                json={"severity": new_sev},
                                timeout=10,
                            )
                            st.rerun()

    # ── Tab 2: Thresholds ──────────────────────────────────────────────
    with tab2:
        t_result = api_get("/v1/config/thresholds")
        if not t_result.get("success"):
            st.error(t_result.get("message"))
        else:
            t_data = t_result["data"]
            auto_above = t_data.get("auto_above", 85)
            manual_below = t_data.get("manual_below", 60)

            st.info(
                f"**Current thresholds:** "
                f"auto ≥ **{auto_above}%** · "
                f"manual < **{manual_below}%** · "
                f"review is everything in between"
            )

            with st.form("update_thresholds"):
                col1, col2 = st.columns(2)
                with col1:
                    new_auto = st.slider(
                        "Auto-process above (%)",
                        min_value=51,
                        max_value=99,
                        value=auto_above,
                        help="Fields with confidence at or above this value are auto-processed",
                    )
                with col2:
                    new_manual = st.slider(
                        "Manual input below (%)",
                        min_value=1,
                        max_value=79,
                        value=manual_below,
                        help="Fields with confidence below this value require manual input",
                    )

                if new_auto <= new_manual:
                    st.error(
                        "auto_above must be greater than manual_below"
                    )
                    submit_disabled = True
                else:
                    st.caption(
                        f"Review range: {new_manual}% – {new_auto}%"
                    )
                    submit_disabled = False

                submitted = st.form_submit_button(
                    "Update Thresholds",
                    type="primary",
                    use_container_width=True,
                    disabled=submit_disabled,
                )

            if submitted and not submit_disabled:
                result = api_post(
                    "/v1/config/thresholds",
                    json={
                        "auto_above": new_auto,
                        "manual_below": new_manual,
                    },
                )
                if result.get("success"):
                    st.success(
                        f"✅ Thresholds updated: "
                        f"auto ≥ {new_auto}% · manual < {new_manual}%"
                    )
                    st.rerun()
                else:
                    st.error(
                        f"❌ {result.get('message', 'Update failed')}"
                    )
