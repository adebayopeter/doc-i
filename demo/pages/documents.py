import time

import requests
import streamlit as st

from api_client import api_delete, api_get, api_post
from constants import API_BASE, HEADERS, STATUS_COLOUR


def render():
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

    if status not in {"complete", "rejected"}:
        _render_upload(selected_sid)

    st.divider()
    _render_document_list(selected_sid, status)


def _render_upload(selected_sid: str):
    upload_mode = st.radio(
        "Upload mode",
        ["Single document", "Multiple documents"],
        horizontal=True,
    )

    if upload_mode == "Single document":
        uploaded_file = st.file_uploader(
            "Upload a document",
            type=["pdf", "png", "jpg", "jpeg", "webp", "tiff"],
            help="PDF, PNG, JPG, WEBP or TIFF — max 200MB",
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
                    with st.spinner("Uploading..."):
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

    else:
        uploaded_files = st.file_uploader(
            "Upload multiple documents (max 10)",
            type=["pdf", "png", "jpg", "jpeg", "webp", "tiff"],
            accept_multiple_files=True,
            help="Select up to 10 files at once",
        )
        if uploaded_files:
            st.caption(
                f"**{len(uploaded_files)} file(s) selected:** "
                + ", ".join(f.name for f in uploaded_files)
            )

            if len(uploaded_files) > 10:
                st.error("Maximum 10 files per upload. Please remove some files.")
            else:
                if st.button(
                    f"Upload & Classify All {len(uploaded_files)} Files",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner(
                        f"Uploading {len(uploaded_files)} documents..."
                    ):
                        files_payload = [
                            (
                                "files",
                                (f.name, f.getvalue(), f.type),
                            )
                            for f in uploaded_files
                        ]
                        response = requests.post(
                            f"/v1/documents/submissions/{selected_sid}/upload-bulk",
                            headers={
                                k: v
                                for k, v in HEADERS.items()
                                if k != "Content-Type"
                            },
                            files=files_payload,
                            timeout=120,
                        )
                        result = response.json()

                    if result.get("success"):
                        data = result["data"]
                        st.success(
                            f"✅ {data['total_uploaded']} document(s) uploaded "
                            f"— classification running..."
                        )
                        for fail in data["failed"]:
                            st.warning(
                                f"⚠️ {fail['filename']}: {fail['reason']}"
                            )
                        st.rerun()
                    else:
                        st.error(
                            f"❌ {result.get('message', 'Bulk upload failed')}"
                        )


def _render_document_list(selected_sid: str, status: str):
    docs_result = api_get(f"/v1/submissions/{selected_sid}/documents")
    if not docs_result.get("success"):
        st.error(f"Could not load documents: {docs_result.get('message')}")
        return

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
                _render_document_detail(doc["document_id"], status)

    # Auto-refresh while any document is still being processed
    pending = sum(
        1 for doc in documents
        if doc["status"] in {"uploaded", "processing"}
    )
    if pending > 0:
        st.info(
            f"⏳ {pending} document(s) still being classified "
            f"— refreshing in 5 seconds..."
        )
        time.sleep(5)
        st.rerun()
    elif total > 0 and classified == total:
        st.success(f"✅ All {classified} documents classified.")


def _render_document_detail(document_id: str, status: str):
    doc_detail = api_get(f"/v1/documents/{document_id}")
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
            rows = [
                {
                    "Field": fn,
                    "Value": d.get("value") or "—",
                    "Confidence": f"{d.get('confidence', 0):.0f}%",
                }
                for fn, d in fields.items()
                if isinstance(d, dict)
            ]
            if rows:
                st.table(rows)
        elif detail.get("status") == "processing":
            st.spinner("Classification still running...")
        elif detail.get("status") == "uploaded":
            st.info("Document uploaded — classification will start shortly.")

        if st.button("Close", key=f"close_{document_id}",):
            st.session_state[f"show_doc_{document_id}"] = False
            st.rerun()

        if status not in {"complete", "rejected"}:
            if st.button("🗑️ Remove", key=f"del_doc_{document_id}"):
                api_delete(f"/v1/documents/{document_id}")
                st.session_state[f"show_doc_{document_id}"] = False
                st.rerun()
