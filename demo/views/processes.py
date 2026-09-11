import requests
import streamlit as st

from api_client import api_delete, api_get, api_post, get_categories
from constants import API_BASE, HEADERS


def render():
    st.title("📁 Processes")
    st.caption(
        "Define document workflows. Each process specifies which documents "
        "are required — the AI uses this checklist to classify uploads."
    )

    # ── Create new process ─────────────────────────────────────────────
    with st.expander("➕ Create New Process", expanded=False):
        st.subheader("Document Checklist")
        st.caption("Add the documents required for this process (minimum 1).")

        num_docs = st.number_input(
            "Number of documents",
            min_value=1,
            max_value=30,
            value=st.session_state.get("num_docs", 3),
            key="num_docs",
        )

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
            st.caption("Fill in all document rows below.")

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
                    all_categories = get_categories()
                    if all_categories:
                        doc_cat = st.selectbox(
                            "Category",
                            options=all_categories,
                            index=0,
                            key=f"doc_cat_{i}",
                        )
                    else:
                        doc_cat = st.text_input(
                            "Category",
                            key=f"doc_cat_{i}",
                            placeholder="No categories yet — add them in Config",
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
                    col1, col2, col3, col4, col5 = st.columns([4, 2, 2, 2, 2])
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
                            "🔍 View",
                            key=f"view_{proc['process_id']}",
                            use_container_width=True,
                        ):
                            st.session_state[
                                f"viewing_{proc['process_id']}"
                            ] = not st.session_state.get(
                                f"viewing_{proc['process_id']}", False
                            )
                            st.rerun()
                    with col3:
                        if st.button(
                                "✏️ Edit",
                                key=f"edit_{proc['process_id']}",
                                use_container_width=True,
                        ):
                            st.session_state[f"editing_{proc['process_id']}"] = (
                                not st.session_state.get(
                                    f"editing_{proc['process_id']}", False
                                )
                            )
                            st.rerun()
                    with col4:
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
                    with col5:
                        if st.button(
                                "🗑️ Deactivate",
                                key=f"del_{proc['process_id']}",
                                use_container_width=True,
                        ):
                            st.session_state[
                                f"confirm_delete_{proc['process_id']}"
                            ] = True
                            st.rerun()

                # ── Deactivate confirmation ────────────────────────────────
                if st.session_state.get(f"confirm_delete_{proc['process_id']}"):
                    st.warning(
                        f"⚠️ Deactivate **{proc['name']}**? "
                        f"It will be hidden from all lists. "
                        f"Existing submissions are unaffected."
                    )
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button(
                                "Yes, deactivate",
                                key=f"confirm_yes_{proc['process_id']}",
                                use_container_width=True,
                        ):
                            result = api_delete(
                                f"/v1/processes/{proc['process_id']}"
                            )
                            st.session_state[
                                f"confirm_delete_{proc['process_id']}"
                            ] = False
                            if result.get("success"):
                                st.success(f"✅ {proc['name']} deactivated.")
                            else:
                                st.error(result.get("message", "Failed"))
                            st.rerun()
                    with col_no:
                        if st.button(
                                "Cancel",
                                key=f"confirm_no_{proc['process_id']}",
                                use_container_width=True,
                        ):
                            st.session_state[
                                f"confirm_delete_{proc['process_id']}"
                            ] = False
                            st.rerun()

                # ── Read-only detail view ──────────────────────────────
                if st.session_state.get(f"viewing_{proc['process_id']}"):
                    _render_process_detail(proc["process_id"])

                # ── Inline edit form ───────────────────────────────────────
                if st.session_state.get(f"editing_{proc['process_id']}"):
                    _render_edit_form(proc)


def _render_edit_form(proc: dict):
    """Renders the inline edit form for a process."""
    detail_result = api_get(f"/v1/processes/{proc['process_id']}")
    detail = detail_result.get("data", {})
    current_docs = detail.get("documents", [])

    with st.expander(f"✏️ Editing: {proc['name']}", expanded=True):
        # Metadata fields outside form for immediate render
        edit_num_docs = st.number_input(
            "Number of documents",
            min_value=1,
            max_value=30,
            value=max(len(current_docs), 1),
            key=f"edit_num_{proc['process_id']}",
        )

        with st.form(key=f"edit_form_{proc['process_id']}"):
            col1, col2 = st.columns(2)
            with col1:
                edit_name = st.text_input(
                    "Process Name",
                    value=detail.get("name", ""),
                )
                edit_desc = st.text_area(
                    "Description",
                    value=detail.get("description") or "",
                    height=80,
                )
            with col2:
                edit_colour = st.selectbox(
                    "Colour",
                    ["info", "success", "warning", "danger"],
                    index=["info", "success", "warning", "danger"].index(
                        detail.get("color_var", "info")
                    ),
                )
                edit_icon = st.text_input(
                    "Icon",
                    value=detail.get("icon", "ti-file"),
                )

            st.subheader("Document Checklist")
            all_categories = get_categories()

            edit_docs = []
            for i in range(int(edit_num_docs)):
                existing = (
                    current_docs[i]
                    if i < len(current_docs)
                    else {}
                )
                c1, c2, c3 = st.columns([4, 3, 2])
                with c1:
                    doc_name = st.text_input(
                        f"Document {i + 1} name",
                        value=existing.get("name", ""),
                        key=f"edit_doc_name_{proc['process_id']}_{i}",
                    )
                with c2:
                    if all_categories:
                        current_cat = existing.get("category", "")
                        cat_index = (
                            all_categories.index(current_cat)
                            if current_cat in all_categories
                            else 0
                        )
                        doc_cat = st.selectbox(
                            "Category",
                            options=all_categories,
                            index=cat_index,
                            key=f"edit_doc_cat_{proc['process_id']}_{i}",
                        )
                    else:
                        doc_cat = st.text_input(
                            "Category",
                            value=existing.get("category", ""),
                            key=f"edit_doc_cat_{proc['process_id']}_{i}",
                        )
                with c3:
                    doc_req = st.checkbox(
                        "Required",
                        value=existing.get("is_required", True),
                        key=f"edit_doc_req_{proc['process_id']}_{i}",
                    )
                if doc_name and doc_cat:
                    edit_docs.append(
                        {
                            "name": doc_name,
                            "category": doc_cat,
                            "is_required": doc_req,
                        }
                    )

            col_save, col_cancel = st.columns(2)
            with col_save:
                save = st.form_submit_button(
                    "💾 Save Changes",
                    type="primary",
                    use_container_width=True,
                )
            with col_cancel:
                cancel = st.form_submit_button(
                    "Cancel",
                    use_container_width=True,
                )

        if save:
            if not edit_name:
                st.error("Process name is required.")
            elif len(edit_docs) == 0:
                st.error(
                    "Fill in at least one complete document "
                    "(name and category both required)."
                )
            else:
                import requests as req

                response = req.patch(
                    f"{API_BASE}/v1/processes/{proc['process_id']}",
                    headers=HEADERS,
                    json={
                        "name": edit_name,
                        "description": edit_desc or None,
                        "color_var": edit_colour,
                        "icon": edit_icon,
                        "documents": edit_docs,
                    },
                    timeout=10,
                )
                result = response.json()
                if result.get("success"):
                    st.success(
                        f"✅ Process updated — "
                        f"{result['data']['document_count']} documents"
                    )
                    st.session_state[
                        f"editing_{proc['process_id']}"
                    ] = False
                    st.rerun()
                else:
                    st.error(
                        f"❌ {result.get('message', 'Update failed')}"
                    )

        if cancel:
            st.session_state[f"editing_{proc['process_id']}"] = False
            st.rerun()

        # ── Extraction fields ──────────────────────────────────────────
        _render_extraction_fields(proc["process_id"])
        _render_validation_rules(proc["process_id"])
        _render_thresholds(proc["process_id"])


def _render_extraction_fields(process_id: str):
    """Renders per-document extraction field configuration."""
    st.divider()
    st.subheader("🔧 Extraction Fields")
    st.caption(
        "Configure which fields Claude extracts from each document type. "
        "Fields are set per document — NIN Slip extracts different fields "
        "than a Bank Statement. Extraction is **disabled** until at least "
        "one document has at least one active field."
    )

    # Load summary across all documents
    summary_result = api_get(f"/v1/processes/{process_id}/fields/summary")
    if not summary_result.get("success"):
        st.error("Could not load field configuration.")
        return

    summary = summary_result.get("data", {})
    extraction_enabled = summary.get("extraction_enabled", False)
    docs_with_fields = summary.get("documents_with_fields", 0)
    total_docs = summary.get("total_documents", 0)

    if extraction_enabled:
        st.success(
            f"✅ Extraction enabled — "
            f"{docs_with_fields}/{total_docs} documents have fields configured"
        )
    else:
        st.error(
            "❌ Extraction disabled — no documents have fields configured. "
            "Expand a document below and add at least one field."
        )

    # Show each document with its fields
    for doc_data in summary.get("documents", []):
        doc_id = doc_data["process_document_id"]
        doc_name = doc_data["document_name"]
        fields_configured = doc_data["fields_configured"]
        active_count = doc_data["active"]

        status_icon = "✅" if fields_configured else "⚠️"
        status_text = (
            f"{active_count} field(s)" if fields_configured else "no fields"
        )

        with st.container(border=True):
            st.markdown(f"{status_icon} **{doc_name}** — {status_text}")

            # Show existing fields for this document
            existing_fields = doc_data.get("items", [])
            if existing_fields:
                for ef in existing_fields:
                    active_icon = "✅" if ef["is_active"] else "⏸️"
                    with st.container(border=True):
                        c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 1])
                        with c1:
                            st.markdown(f"{active_icon} **{ef['name']}**")
                            if ef.get("description"):
                                st.caption(ef["description"])
                        with c2:
                            st.caption(
                                "📊 In decision"
                                if ef["include_in_decision"]
                                else "⬜ Excluded"
                            )
                        with c3:
                            st.caption(
                                "⚠️ null → manual"
                                if ef["null_is_manual"]
                                else "null → skip"
                            )
                        with c4:
                            toggle_label = (
                                "Disable" if ef["is_active"] else "Enable"
                            )
                            if st.button(
                                toggle_label,
                                key=f"ef_toggle_{ef['id']}",
                                use_container_width=True,
                            ):
                                requests.patch(
                                    f"{API_BASE}/v1/processes/{process_id}"
                                    f"/documents/{doc_id}/fields/{ef['id']}",
                                    headers=HEADERS,
                                    json={"is_active": not ef["is_active"]},
                                    timeout=10,
                                )
                                st.rerun()
                        with c5:
                            if st.button(
                                "🗑️",
                                key=f"ef_del_{ef['id']}",
                                use_container_width=True,
                                help="Remove this field",
                            ):
                                requests.delete(
                                    f"{API_BASE}/v1/processes/{process_id}"
                                    f"/documents/{doc_id}/fields/{ef['id']}",
                                    headers=HEADERS,
                                    timeout=10,
                                )
                                st.rerun()
            else:
                st.info(
                    f"No fields configured for **{doc_name}** yet. "
                    f"Add fields below — this document will be classified "
                    f"but no data will be extracted until fields are added."
                )

            # Add new field form
            st.markdown("**Add a field:**")
            with st.form(key=f"add_field_{process_id}_{doc_id}"):
                fc1, fc2 = st.columns(2)
                with fc1:
                    new_field_name = st.text_input(
                        "Field Name *",
                        placeholder="e.g. Full Name",
                        key=f"fn_{process_id}_{doc_id}",
                    )
                    new_field_desc = st.text_input(
                        "Description",
                        placeholder="e.g. Legal full name",
                        key=f"fd_{process_id}_{doc_id}",
                    )
                with fc2:
                    new_include = st.checkbox(
                        "Include in routing decision",
                        value=True,
                        key=f"fi_{process_id}_{doc_id}",
                        help=(
                            "If checked, this field's confidence score "
                            "affects the auto/review/manual routing verdict"
                        ),
                    )
                    new_null_manual = st.checkbox(
                        "Missing value → manual",
                        value=False,
                        key=f"fm_{process_id}_{doc_id}",
                        help=(
                            "If checked, a null or missing value forces "
                            "manual routing. Use for required fields."
                        ),
                    )
                    new_sort = st.number_input(
                        "Sort order",
                        min_value=0,
                        value=len(existing_fields),
                        key=f"fs_{process_id}_{doc_id}",
                    )

                add_submit = st.form_submit_button(
                    "➕ Add Field",
                    type="primary",
                    use_container_width=True,
                )

            if add_submit:
                if not new_field_name:
                    st.error("Field name is required.")
                else:
                    resp = requests.post(
                        f"{API_BASE}/v1/processes/{process_id}"
                        f"/documents/{doc_id}/fields",
                        headers=HEADERS,
                        json={
                            "name": new_field_name,
                            "description": new_field_desc or None,
                            "include_in_decision": new_include,
                            "null_is_manual": new_null_manual,
                            "sort_order": new_sort,
                        },
                        timeout=10,
                    )
                    result = resp.json()
                    if result.get("success"):
                        st.success(f"✅ **{new_field_name}** added to {doc_name}.")
                        st.rerun()
                    else:
                        st.error(f"❌ {result.get('message', 'Failed')}")


def _render_validation_rules(process_id: str):
    """Renders process-scoped validation rules section."""
    st.divider()
    st.subheader("✅ Validation Rules")
    st.caption(
        "Rules added here run only for this process, in addition to "
        "the global rules in Config. Use process rules for workflow-specific "
        "checks — e.g. Property Value required for RSA Mortgage only."
    )

    result = api_get(f"/v1/processes/{process_id}/rules")
    if not result.get("success"):
        st.error("Could not load validation rules.")
        return

    data = result.get("data", {})
    rules = data.get("items", [])
    global_count = data.get("global_count", 0)
    process_count = data.get("process_count", 0)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Rules", data.get("total", 0))
    col2.metric("Global", global_count)
    col3.metric("This Process Only", process_count)

    st.divider()

    # Show process-scoped rules with delete option
    process_rules = [r for r in rules if r["scope"] == "process"]
    global_rules = [r for r in rules if r["scope"] == "global"]

    if process_rules:
        st.markdown("**Process-specific rules:**")
        for rule in process_rules:
            enabled_icon = "✅" if rule["is_enabled"] else "⏸️"
            sev_icon = "🔴" if rule["severity"] == "error" else "🟡"
            with st.container(border=True):
                c1, c2, c3 = st.columns([5, 2, 2])
                with c1:
                    st.markdown(f"{enabled_icon} **{rule['name']}**")
                    details = []
                    if rule.get("check"):
                        details.append(f"check: `{rule['check']}`")
                    if rule.get("pattern"):
                        details.append(f"pattern: `{rule['pattern']}`")
                    if details:
                        st.caption(" · ".join(details))
                    st.caption(
                        f"`{rule['id']}` · {sev_icon} {rule['severity']} "
                        f"· {rule['rule_type']} · field: {rule['field']}"
                    )
                with c2:
                    toggle_label = (
                        "Disable" if rule["is_enabled"] else "Enable"
                    )
                    if st.button(
                        toggle_label,
                        key=f"rule_toggle_{rule['id']}",
                        use_container_width=True,
                    ):
                        requests.patch(
                            f"{API_BASE}/v1/config/rules/{rule['id']}",
                            headers=HEADERS,
                            json={"enabled": not rule["is_enabled"]},
                            timeout=10,
                        )
                        st.rerun()
                with c3:
                    if st.button(
                        "🗑️ Delete",
                        key=f"rule_del_{rule['id']}",
                        use_container_width=True,
                    ):
                        requests.delete(
                            f"{API_BASE}/v1/config/rules/{rule['id']}",
                            headers=HEADERS,
                            timeout=10,
                        )
                        st.rerun()

    if global_rules:
        with st.container(border=True):
            st.markdown(
                f"📋 **{len(global_rules)} global rules also apply to this process**"
            )
            for rule in global_rules:
                enabled_icon = "✅" if rule["is_enabled"] else "⏸️"
                st.markdown(
                    f"{enabled_icon} **{rule['name']}** "
                    f"[{rule['rule_type']}] — `{rule['field']}`"
                )
            st.caption(
                "To manage global rules, go to ⚙️ Config → Validation Rules."
            )

    # Add new process-scoped rule
    st.markdown("**Add a rule for this process:**")
    with st.form(key=f"add_rule_{process_id}"):
        col1, col2 = st.columns(2)
        with col1:
            rule_name = st.text_input(
                "Rule Name *",
                placeholder="e.g. Property value required",
            )
            rule_field = st.text_input(
                "Field *",
                placeholder="e.g. Property Value",
            )
            rule_type = st.selectbox(
                "Rule Type *",
                ["required", "format", "logical", "cross_doc"],
            )
        with col2:
            rule_severity = st.selectbox("Severity", ["error", "warning"])
            rule_pattern = st.text_input(
                "Pattern (format rules only)",
                placeholder=r"e.g. ^\d{11}$",
            )
            rule_check = st.selectbox(
                "Check (logical rules only)",
                ["", "not_future", "min_age_18", "not_expired"],
            )

        add_rule_submit = st.form_submit_button(
            "➕ Add Rule",
            type="primary",
            use_container_width=True,
        )

    if add_rule_submit:
        if not rule_name or not rule_field:
            st.error("Rule name and field are required.")
        elif rule_type == "format" and not rule_pattern:
            st.error("Pattern is required for format rules.")
        elif rule_type == "logical" and not rule_check:
            st.error("Check is required for logical rules.")
        else:
            resp = requests.post(
                f"{API_BASE}/v1/processes/{process_id}/rules",
                headers=HEADERS,
                json={
                    "name": rule_name,
                    "rule_type": rule_type,
                    "field": rule_field,
                    "severity": rule_severity,
                    "pattern": rule_pattern or None,
                    "check": rule_check or None,
                },
                timeout=10,
            )
            result = resp.json()
            if result.get("success"):
                st.success(f"✅ Rule **{rule_name}** added.")
                st.rerun()
            else:
                st.error(f"❌ {result.get('message', 'Failed')}")


def _render_thresholds(process_id: str):
    """Renders process-specific confidence threshold configuration."""
    st.divider()
    st.subheader("🎚️ Confidence Thresholds")
    st.caption(
        "Override the global confidence thresholds for this process. "
        "Leave as global default unless this process needs stricter "
        "or more lenient routing."
    )

    result = api_get(f"/v1/processes/{process_id}/thresholds")
    if not result.get("success"):
        st.error("Could not load threshold configuration.")
        return

    data = result.get("data", {})
    is_override = data.get("is_override", False)
    auto_above = data.get("auto_above", 85)
    manual_below = data.get("manual_below", 60)

    if is_override:
        st.info(
            f"🔧 **Custom thresholds active** — "
            f"auto ≥ {auto_above}% · manual < {manual_below}% · "
            f"review is {manual_below}%–{auto_above}%"
        )
    else:
        st.info(
            f"🌐 **Using global default** — "
            f"auto ≥ {auto_above}% · manual < {manual_below}%. "
            f"Set an override below to customise for this process."
        )

    with st.form(key=f"threshold_form_{process_id}"):
        col1, col2 = st.columns(2)
        with col1:
            new_auto = st.slider(
                "Auto-process above (%)",
                min_value=51,
                max_value=99,
                value=auto_above,
                help="Fields at or above this confidence are auto-processed",
            )
        with col2:
            new_manual = st.slider(
                "Manual input below (%)",
                min_value=1,
                max_value=79,
                value=manual_below,
                help="Fields below this confidence require manual input",
            )

        if new_auto <= new_manual:
            st.error("auto-process threshold must be greater than manual threshold")
            disabled = True
        else:
            st.caption(
                f"Review range: {new_manual}% – {new_auto}%"
            )
            disabled = False

        col_save, col_reset = st.columns(2)
        with col_save:
            save = st.form_submit_button(
                "💾 Save Override",
                type="primary",
                use_container_width=True,
                disabled=disabled,
            )
        with col_reset:
            reset = st.form_submit_button(
                "🔄 Revert to Global",
                use_container_width=True,
                disabled=not is_override,
            )

    if save and not disabled:
        resp = requests.put(
            f"{API_BASE}/v1/processes/{process_id}/thresholds",
            headers=HEADERS,
            json={"auto_above": new_auto, "manual_below": new_manual},
            timeout=10,
        )
        result = resp.json()
        if result.get("success"):
            st.success(
                f"✅ Thresholds set: auto ≥ {new_auto}% · "
                f"manual < {new_manual}%"
            )
            st.rerun()
        else:
            st.error(f"❌ {result.get('message', 'Failed')}")

    if reset:
        resp = requests.delete(
            f"{API_BASE}/v1/processes/{process_id}/thresholds",
            headers=HEADERS,
            timeout=10,
        )
        result = resp.json()
        if result.get("success"):
            st.success("✅ Reverted to global defaults.")
            st.rerun()
        else:
            st.error(f"❌ {result.get('message', 'Failed')}")


def _render_process_detail(process_id: str):
    """Read-only process detail — checklist, fields, rules, thresholds."""
    detail_result = api_get(f"/v1/processes/{process_id}")
    if not detail_result.get("success"):
        st.error("Could not load process details.")
        return

    detail = detail_result.get("data", {})

    with st.container(border=True):
        st.markdown(f"### 📋 {detail.get('name')}")
        if detail.get("description"):
            st.caption(detail["description"])
        st.caption(f"`{process_id}`")

        st.divider()

        # ── Document checklist ─────────────────────────────────────────
        st.markdown("**Document Checklist**")
        documents = detail.get("documents", [])
        for doc in documents:
            req_icon = "🔴" if doc.get("is_required") else "⚪"
            st.markdown(
                f"{req_icon} **{doc['name']}** — "
                f"*{doc.get('category', '—')}*"
            )

        st.divider()

        # ── Extraction fields summary ──────────────────────────────────
        st.markdown("**Extraction Fields**")
        summary_result = api_get(f"/v1/processes/{process_id}/fields/summary")
        if summary_result.get("success"):
            summary = summary_result.get("data", {})
            extraction_enabled = summary.get("extraction_enabled", False)

            if extraction_enabled:
                st.success(
                    f"✅ Extraction enabled — "
                    f"{summary.get('documents_with_fields', 0)}/"
                    f"{summary.get('total_documents', 0)} documents configured"
                )
            else:
                st.error("❌ Extraction disabled — no fields configured")

            for doc_data in summary.get("documents", []):
                doc_name = doc_data["document_name"]
                fields = doc_data.get("items", [])
                active_fields = [f for f in fields if f["is_active"]]

                if active_fields:
                    field_names = ", ".join(f["name"] for f in active_fields)
                    st.caption(f"📄 **{doc_name}**: {field_names}")
                else:
                    st.caption(f"📄 **{doc_name}**: *no fields configured*")

        st.divider()

        # ── Validation rules summary ───────────────────────────────────
        st.markdown("**Validation Rules**")
        rules_result = api_get(f"/v1/processes/{process_id}/rules")
        if rules_result.get("success"):
            rules_data = rules_result.get("data", {})
            global_count = rules_data.get("global_count", 0)
            process_count = rules_data.get("process_count", 0)
            col1, col2, col3 = st.columns(3)
            col1.metric("Total", rules_data.get("total", 0))
            col2.metric("🌐 Global", global_count)
            col3.metric("🏠 Process-specific", process_count)

        st.divider()

        # ── Threshold summary ──────────────────────────────────────────
        st.markdown("**Confidence Thresholds**")
        thr_result = api_get(f"/v1/processes/{process_id}/thresholds")
        if thr_result.get("success"):
            thr = thr_result.get("data", {})
            is_override = thr.get("is_override", False)
            auto_above = thr.get("auto_above", 85)
            manual_below = thr.get("manual_below", 60)
            scope_label = "🔧 Custom override" if is_override else "🌐 Global default"
            st.caption(
                f"{scope_label} — "
                f"auto ≥ **{auto_above}%** · "
                f"manual < **{manual_below}%** · "
                f"review **{manual_below}%–{auto_above}%**"
            )

        st.divider()
        st.caption(
            "Click **✏️ Edit** to modify this process configuration."
        )
