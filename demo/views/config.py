import requests
import streamlit as st

from api_client import api_delete, api_get, api_post
from constants import API_BASE, HEADERS


def render():
    st.title("⚙️ Configuration")
    st.caption(
        "Manage validation rules and confidence thresholds. "
        "Changes take effect immediately."
    )

    tab1, tab2, tab3 = st.tabs(["📏 Validation Rules", "🎚️ Thresholds", "📂 Categories"])

    # ── Tab 1: Validation rules ────────────────────────────────────────
    with tab1:
        _render_rules()

    # ── Tab 2: Thresholds ──────────────────────────────────────────────
    with tab2:
        _render_thresholds()

    # ── Tab 3: Categories ──────────────────────────────────────────────
    with tab3:
        _render_categories()


def _render_rules():
    with st.expander("➕ Create New Validation Rule", expanded=False):

        # Load processes for the dropdown
        proc_result = api_get("/v1/processes")
        processes = proc_result.get("data", {}).get("items", [])
        process_options = {"🌐 Global (applies to all processes)": None}
        process_options.update({p["name"]: p["process_id"] for p in processes})

        with st.form("create_rule"):
            col1, col2 = st.columns(2)
            with col1:
                rule_name = st.text_input(
                    "Rule Name *",
                    placeholder="e.g. NIN must be 11 digits",
                )
                rule_field = st.text_input(
                    "Field *",
                    placeholder="e.g. NIN",
                    help="The document field this rule applies to",
                )
                rule_type = st.selectbox(
                    "Rule Type *",
                    ["required", "format", "logical", "cross_doc"],
                    help=(
                        "required — field must be present\n"
                        "format — field must match a regex pattern\n"
                        "logical — date/age/expiry check\n"
                        "cross_doc — value must match across documents"
                    ),
                )
                rule_severity = st.selectbox(
                    "Severity",
                    ["error", "warning"],
                    help=(
                        "error — failure blocks auto-processing\n"
                        "warning — flagged but does not block"
                    ),
                )
            with col2:
                rule_pattern = st.text_input(
                    "Pattern (format rules only)",
                    placeholder=r"e.g. ^\d{11}$",
                    help="Regex pattern the field value must match",
                )
                rule_check = st.selectbox(
                    "Check (logical rules only)",
                    ["", "not_future", "min_age_18", "not_expired"],
                    help="Which logical check to run on the field value",
                )
                # Process scope selector
                selected_process_name = st.selectbox(
                    "Scope",
                    options=list(process_options.keys()),
                    index=0,
                    help=(
                        "Global — runs on every process. "
                        "Choose a process to restrict this rule to that "
                        "workflow only."
                    ),
                )
                selected_process_id = process_options[selected_process_name]

            # Show contextual help based on rule type
            if rule_type == "required":
                st.info(
                    "💡 Required rule — the field must be present and "
                    "not null. No pattern or check needed."
                )
            elif rule_type == "format":
                st.info(
                    "💡 Format rule — field value must match the regex "
                    "pattern. Example: `^\\d{11}$` for an 11-digit NIN."
                )
            elif rule_type == "logical":
                st.info(
                    "💡 Logical rule — runs a date or age check. "
                    "Select a check from the dropdown above."
                )
            elif rule_type == "cross_doc":
                st.info(
                    "💡 Cross-document rule — checks that this field "
                    "has the same value across all classified documents. "
                    "No pattern or check needed."
                )

            rule_submitted = st.form_submit_button(
                "Create Rule", type="primary", use_container_width=True
            )

        if rule_submitted:
            if not rule_name:
                st.error("Rule name is required.")
            elif not rule_field:
                st.error("Field is required.")
            elif rule_type == "format" and not rule_pattern:
                st.error(
                    "Pattern is required for format rules. "
                    r"Example: ^\d{11}$ for an 11-digit number."
                )
            elif rule_type == "logical" and not rule_check:
                st.error(
                    "Check is required for logical rules. "
                    "Select one from the dropdown."
                )
            else:
                payload = {
                    "name": rule_name,
                    "rule_type": rule_type,
                    "field": rule_field,
                    "severity": rule_severity,
                    "pattern": rule_pattern or None,
                    "check": rule_check or None,
                    "process_id": selected_process_id,
                }

                response = requests.post(
                    f"{API_BASE}/v1/config/rules",
                    headers=HEADERS,
                    json=payload,
                    timeout=10,
                )
                result_data = response.json()
                if result_data.get("success"):
                    scope = (
                        "globally"
                        if not selected_process_id
                        else f"for {selected_process_name}"
                    )
                    st.success(
                        f"✅ Rule **{rule_name}** created {scope}."
                    )
                    st.rerun()
                else:
                    st.error(
                        f"❌ {result_data.get('message', 'Failed to create rule')}"
                    )

    st.divider()

    result = api_get("/v1/config/rules")
    if not result.get("success"):
        st.error(result.get("message"))
        return

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
                scope_badge = (
                    "🌐 Global"
                    if rule.get("scope") == "global"
                    else "🏠 Process"
                )
                st.markdown(
                    f"{enabled_icon} **{rule['name']}** "
                    f"<small>{scope_badge}</small>",
                    unsafe_allow_html=True,
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
                toggle_label = ("Disable" if rule["is_enabled"] else "Enable")
                if st.button(
                        toggle_label,
                        key=f"toggle_{rule['id']}",
                        use_container_width=True,
                ):
                    requests.patch(
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
                    requests.patch(
                        f"{API_BASE}/v1/config/rules/{rule['id']}",
                        headers=HEADERS,
                        json={"severity": new_sev},
                        timeout=10,
                    )
                    st.rerun()


def _render_thresholds():
    t_result = api_get("/v1/config/thresholds")
    if not t_result.get("success"):
        st.error(t_result.get("message"))
        return

    t_data = t_result["data"]
    auto_above = t_data.get("auto_above", 85)
    manual_below = t_data.get("manual_below", 60)

    st.info(
        f"**Global default thresholds:** "
        f"auto ≥ **{auto_above}%** · "
        f"manual < **{manual_below}%** · "
        f"review is everything in between. "
        f"Individual processes can override these in their settings."
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
            st.error("auto_above must be greater than manual_below")
            submit_disabled = True
        else:
            st.caption(f"Review range: {new_manual}% – {new_auto}%")
            submit_disabled = False

        submitted = st.form_submit_button(
            "Update Thresholds",
            type="primary",
            use_container_width=True,
            disabled=submit_disabled,
        )

    if submitted and not submit_disabled:
        result = requests.put(
            f"{API_BASE}/v1/config/thresholds",
            headers=HEADERS,
            json={"auto_above": new_auto, "manual_below": new_manual},
            timeout=10,
        ).json()
        if result.get("success"):
            st.success(
                f"✅ Thresholds updated: "
                f"auto ≥ {new_auto}% · manual < {new_manual}%"
            )
            st.rerun()
        else:
            st.error(f"❌ {result.get('message', 'Update failed')}")


def _render_categories():
    st.subheader("Document Categories")
    st.caption(
        "Create categories here first. They appear as dropdowns "
        "when configuring document checklists on processes."
    )

    # Create new category
    with st.form("create_category"):
        col1, col2 = st.columns([3, 4])
        with col1:
            new_cat_name = st.text_input(
                "Category Name *",
                placeholder="e.g. Identity",
            )
        with col2:
            new_cat_desc = st.text_input(
                "Description",
                placeholder="e.g. Government-issued identity documents",
            )
        cat_submitted = st.form_submit_button(
            "Add Category", type="primary", use_container_width=True
        )

    if cat_submitted:
        if not new_cat_name:
            st.error("Category name is required.")
        else:
            result = api_post(
                "/v1/config/categories",
                json={
                    "name": new_cat_name,
                    "description": new_cat_desc or None,
                },
            )
            if result.get("success"):
                st.success(f"✅ Category **{new_cat_name}** added successfully.")
                st.rerun()
            else:
                st.error(f"❌ {result.get('message', 'Failed to add category')}")

    st.divider()

    # List and manage categories
    cat_result = api_get("/v1/config/categories?include_inactive=true")
    if not cat_result.get("success"):
        st.error(cat_result.get("message"))
        return

    cat_data = cat_result["data"]
    categories = cat_data.get("items", [])
    total = cat_data.get("total", 0)
    active = cat_data.get("active", 0)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total", total)
    col2.metric("Active", active)
    col3.metric("Inactive", total - active)

    st.divider()

    if total == 0:
        st.info(
            "No categories yet. Add your first one above.\n\n"
            "**Suggested categories for Nigerian document processing:**\n"
            "Identity · Financial · Income · Supporting · Legal · Property"
        )
        return

    for cat in categories:
        active_icon = "✅" if cat["is_active"] else "⏸️"
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 4, 2, 2])
            with col1:
                st.markdown(
                    f"{active_icon} **{cat['name']}**"
                )
                st.caption(f"`{cat['id']}`")
            with col2:
                desc = cat.get("description") or "—"
                st.caption(desc)
            with col3:
                toggle_label = (
                    "Deactivate" if cat["is_active"] else "Reactivate"
                )
                if st.button(
                        toggle_label,
                        key=f"cat_toggle_{cat['id']}",
                        use_container_width=True,
                ):
                    if cat["is_active"]:
                        api_delete(f"/v1/config/categories/{cat['id']}")
                    else:
                        api_post(
                            "/v1/config/categories",
                            json={"name": cat["name"]},
                        )
                    st.rerun()
            with col4:
                if st.button(
                    "✏️ Rename",
                    key=f"cat_rename_{cat['id']}",
                    use_container_width=True,
                ):
                    st.session_state[f"renaming_{cat['id']}"] = True

        # Inline rename form
        if st.session_state.get(f"renaming_{cat['id']}"):
            with st.form(key=f"rename_form_{cat['id']}"):
                new_name = st.text_input(
                    "New name",
                    value=cat["name"],
                    key=f"rename_input_{cat['id']}",
                )
                new_desc = st.text_input(
                    "New description",
                    value=cat.get("description") or "",
                    key=f"rename_desc_{cat['id']}",
                )
                col_save, col_cancel = st.columns(2)
                with col_save:
                    save = st.form_submit_button("Save", use_container_width=True)
                with col_cancel:
                    cancel = st.form_submit_button("Cancel", use_container_width=True)

            if save:
                requests.patch(
                    f"{API_BASE}/v1/config/categories/{cat['id']}",
                    headers=HEADERS,
                    json={
                        "name": new_name,
                        "description": new_desc or None,
                    },
                    timeout=10,
                )
                st.session_state[f"renaming_{cat['id']}"] = False
                st.rerun()
            if cancel:
                st.session_state[f"renaming_{cat['id']}"] = False
                st.rerun()
