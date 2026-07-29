"""
API Keys management page.

Allows admin users to create, view, rotate, and revoke per-process API keys
for developers integrating with the Doc-I platform.
"""

import requests
import streamlit as st
from datetime import datetime, timedelta

from api_client import api_delete, api_get, api_post
from constants import API_BASE, HEADERS


def render():
    st.title("API Keys")
    st.caption(
        "Manage per-process API keys for developers integrating with the Doc-I platform. "
        "Each key can be scoped to specific processes and has configurable permissions."
    )

    # ── Create new key ──────────────────────────────────────────────────
    with st.expander("Create New Key", expanded=False):
        _render_create_key_form()

    # ── Show newly created key if present ───────────────────────────────
    if st.session_state.get("new_api_key"):
        _render_new_key_banner()

    st.divider()

    # ── List existing keys ──────────────────────────────────────────────
    _render_key_list()


def _render_create_key_form():
    """Renders the form to create a new API key."""
    # Fetch processes for the multiselect
    processes_result = api_get("/v1/processes")
    processes = []
    process_map = {}  # name -> id
    if processes_result.get("success"):
        processes = processes_result.get("data", {}).get("items", [])
        process_map = {p["name"]: p["process_id"] for p in processes}

    with st.form("create_api_key"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input(
                "Key Name *",
                placeholder="e.g. Benefits App - Production",
                help="A descriptive name to identify this key",
            )
            selected_process_names = st.multiselect(
                "Process Access",
                options=list(process_map.keys()),
                help="Select processes this key can access",
            )
            st.caption(
                "Leave empty to grant access to **ALL processes** (admin key)."
            )

        with col2:
            scopes = st.multiselect(
                "Scopes",
                options=["read", "write"],
                default=["read", "write"],
                help="'read' = GET only, 'write' = all methods",
            )
            expires_enabled = st.checkbox(
                "Set expiry date",
                value=False,
            )
            if expires_enabled:
                expires_date = st.date_input(
                    "Expires on",
                    value=datetime.now().date() + timedelta(days=90),
                    min_value=datetime.now().date() + timedelta(days=1),
                )
            else:
                expires_date = None

        submitted = st.form_submit_button(
            "Create Key",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not name:
            st.error("Key name is required.")
        elif not scopes:
            st.error("At least one scope is required.")
        else:
            # Convert process names to IDs
            process_ids = [process_map[n] for n in selected_process_names]

            payload = {
                "name": name,
                "process_ids": process_ids,
                "scopes": scopes,
            }
            if expires_date:
                payload["expires_at"] = f"{expires_date}T23:59:59Z"

            result = api_post("/v1/admin/keys", json=payload)
            if result.get("success"):
                # Store the full key in session state so it persists across reruns
                data = result.get("data", {})
                st.session_state["new_api_key"] = data.get("key")
                st.session_state["new_api_key_name"] = data.get("name")
                st.rerun()
            else:
                st.error(f"Failed to create key: {result.get('message', 'Unknown error')}")


def _render_new_key_banner():
    """Renders the banner showing the newly created API key."""
    st.success("API key created successfully!")
    st.warning(
        "**Copy this key now — it will not be shown again.**\n\n"
        "Store it securely. You cannot retrieve it later."
    )
    st.code(st.session_state["new_api_key"], language=None)
    st.caption(f"Key name: **{st.session_state.get('new_api_key_name', 'Unknown')}**")

    if st.button("Dismiss", key="dismiss_new_key"):
        del st.session_state["new_api_key"]
        if "new_api_key_name" in st.session_state:
            del st.session_state["new_api_key_name"]
        st.rerun()


def _render_key_list():
    """Renders the list of existing API keys."""
    result = api_get("/v1/admin/keys")
    if not result.get("success"):
        st.error(f"Could not load API keys: {result.get('message')}")
        return

    data = result.get("data", {})
    keys = data.get("items", [])
    total = data.get("total", 0)

    st.subheader(f"All API Keys ({total})")

    if total == 0:
        st.info("No API keys yet. Create one above to get started.")
        return

    # Fetch processes for name resolution
    processes_result = api_get("/v1/processes")
    process_id_to_name = {}
    if processes_result.get("success"):
        for p in processes_result.get("data", {}).get("items", []):
            process_id_to_name[p["process_id"]] = p["name"]

    for key in keys:
        _render_key_card(key, process_id_to_name)


def _render_key_card(key: dict, process_id_to_name: dict):
    """Renders a single API key card."""
    key_id = key["id"]
    is_active = key.get("is_active", True)
    status_icon = "Active" if is_active else "Disabled"

    with st.container(border=True):
        col1, col2, col3, col4 = st.columns([4, 2, 2, 2])

        with col1:
            st.markdown(f"**{key['name']}**")
            st.caption(f"`{key.get('key_prefix', 'doci_key_...')}...` (masked)")

            # Process access
            process_ids = key.get("process_ids", [])
            if not process_ids:
                st.caption("Access: **All processes** (admin)")
            else:
                process_names = [
                    process_id_to_name.get(pid, pid) for pid in process_ids
                ]
                st.caption(f"Access: {', '.join(process_names)}")

            # Scopes and status
            scopes = key.get("scopes", ["read", "write"])
            scope_str = ", ".join(scopes)
            st.caption(
                f"Scopes: `{scope_str}` | "
                f"Status: {'Active' if is_active else 'Disabled'} | "
                f"Requests: {key.get('request_count', 0)}"
            )

            # Last used
            last_used = key.get("last_used_at")
            if last_used:
                st.caption(f"Last used: {last_used[:19].replace('T', ' ')}")
            else:
                st.caption("Last used: Never")

        with col2:
            toggle_label = "Disable" if is_active else "Enable"
            if st.button(
                toggle_label,
                key=f"toggle_{key_id}",
                use_container_width=True,
            ):
                _toggle_key(key_id, not is_active)

        with col3:
            if st.button(
                "Rotate",
                key=f"rotate_{key_id}",
                use_container_width=True,
            ):
                st.session_state[f"confirm_rotate_{key_id}"] = True
                st.rerun()

        with col4:
            if st.button(
                "Revoke",
                key=f"revoke_{key_id}",
                use_container_width=True,
            ):
                st.session_state[f"confirm_revoke_{key_id}"] = True
                st.rerun()

        # ── Rotate confirmation ─────────────────────────────────────────
        if st.session_state.get(f"confirm_rotate_{key_id}"):
            st.warning(
                f"Rotate key **{key['name']}**? "
                f"The current key will stop working immediately."
            )
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button(
                    "Yes, rotate",
                    key=f"confirm_rotate_yes_{key_id}",
                    use_container_width=True,
                ):
                    _rotate_key(key_id, key["name"])
            with col_no:
                if st.button(
                    "Cancel",
                    key=f"confirm_rotate_no_{key_id}",
                    use_container_width=True,
                ):
                    st.session_state[f"confirm_rotate_{key_id}"] = False
                    st.rerun()

        # ── Revoke confirmation ─────────────────────────────────────────
        if st.session_state.get(f"confirm_revoke_{key_id}"):
            st.warning(
                f"Revoke key **{key['name']}**? "
                f"This action cannot be undone."
            )
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button(
                    "Yes, revoke",
                    key=f"confirm_revoke_yes_{key_id}",
                    use_container_width=True,
                ):
                    _revoke_key(key_id, key["name"])
            with col_no:
                if st.button(
                    "Cancel",
                    key=f"confirm_revoke_no_{key_id}",
                    use_container_width=True,
                ):
                    st.session_state[f"confirm_revoke_{key_id}"] = False
                    st.rerun()

        # ── Show rotated key if present ─────────────────────────────────
        if st.session_state.get(f"rotated_key_{key_id}"):
            st.success("Key rotated successfully!")
            st.warning(
                "**Copy this new key now — it will not be shown again.**"
            )
            st.code(st.session_state[f"rotated_key_{key_id}"], language=None)
            if st.button("Dismiss", key=f"dismiss_rotated_{key_id}"):
                del st.session_state[f"rotated_key_{key_id}"]
                st.rerun()


def _toggle_key(key_id: str, new_is_active: bool):
    """Enable or disable an API key."""
    response = requests.patch(
        f"{API_BASE}/v1/admin/keys/{key_id}",
        headers=HEADERS,
        json={"is_active": new_is_active},
        timeout=10,
    )
    result = response.json()
    if result.get("success"):
        action = "enabled" if new_is_active else "disabled"
        st.success(f"Key {action}.")
        st.rerun()
    else:
        st.error(f"Failed: {result.get('message', 'Unknown error')}")


def _rotate_key(key_id: str, key_name: str):
    """Rotate an API key and show the new key."""
    st.session_state[f"confirm_rotate_{key_id}"] = False

    response = requests.post(
        f"{API_BASE}/v1/admin/keys/{key_id}/rotate",
        headers=HEADERS,
        timeout=10,
    )
    result = response.json()
    if result.get("success"):
        new_key = result.get("data", {}).get("key")
        st.session_state[f"rotated_key_{key_id}"] = new_key
        st.rerun()
    else:
        st.error(f"Failed to rotate: {result.get('message', 'Unknown error')}")
        st.rerun()


def _revoke_key(key_id: str, key_name: str):
    """Revoke (delete) an API key."""
    st.session_state[f"confirm_revoke_{key_id}"] = False

    result = api_delete(f"/v1/admin/keys/{key_id}")
    if result.get("success"):
        st.success(f"Key **{key_name}** revoked.")
        st.rerun()
    else:
        st.error(f"Failed to revoke: {result.get('message', 'Unknown error')}")
        st.rerun()
