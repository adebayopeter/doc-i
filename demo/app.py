"""
Doc-I — Document Intelligence Platform
Streamlit Demo Application

Entry point — sidebar navigation and page routing only.
Each page lives in pages/ as a standalone module.
"""

import hmac

import streamlit as st

from api_client import check_api_health
from constants import API_BASE, DEMO_PASSWORD
from views import analysis, api_keys, config, documents, processes, submissions

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Doc-I — Document Intelligence",
    page_icon="\U0001F4C4",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ─────────────────────────────────────────────────
for key, value in {
    "selected_process_id": None,
    "selected_submission_id": None,
    "active_page": "Processes",
    "categories_cache": None,
    "authenticated": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ── Password gate ──────────────────────────────────────────────────────────
def check_password() -> bool:
    """
    Returns True if no password is configured or if user has authenticated.
    Shows a login form if password is required but user is not authenticated.
    """
    # No password configured — allow access
    if not DEMO_PASSWORD:
        return True

    # Already authenticated
    if st.session_state.get("authenticated"):
        return True

    # Show login form
    st.markdown(
        """
        <div style="display: flex; justify-content: center; margin-top: 100px;">
            <div style="text-align: center;">
                <img src="https://img.icons8.com/fluency/96/document.png" width="80">
                <h1>Doc-I Platform</h1>
                <p style="color: #666;">Document Intelligence Demo</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Enter Password")
        password = st.text_input(
            "Password",
            type="password",
            label_visibility="collapsed",
            placeholder="Enter demo password",
        )

        if st.button("Log in", type="primary", use_container_width=True):
            # Use hmac.compare_digest to avoid timing attacks
            if hmac.compare_digest(password, DEMO_PASSWORD):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password")

    return False


# ── Password check ─────────────────────────────────────────────────────────
if not check_password():
    st.stop()


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/document.png", width=60)
    st.title("Doc-I Platform")
    st.caption("Document Intelligence Demo")
    st.divider()

    # API health check
    if check_api_health():
        st.success("API connected")
    else:
        st.error("API unreachable")
        st.caption(f"Trying: {API_BASE}")
        st.stop()

    st.divider()

    PAGES = [
        "Processes",
        "Submissions",
        "Documents",
        "Analysis",
        "Config",
        "API Keys",
    ]
    ICON_MAP = {
        "Processes": "\U0001F3E0",
        "Submissions": "\U0001F4CB",
        "Documents": "\U0001F4C4",
        "Analysis": "\U0001F50D",
        "Config": "\U00002699\U0000FE0F",
        "API Keys": "\U0001F511",
    }

    current = f"{ICON_MAP[st.session_state.active_page]} {st.session_state.active_page}"

    page = st.radio(
        "Navigate",
        [f"{ICON_MAP[p]} {p}" for p in PAGES],
        index=PAGES.index(st.session_state.active_page),
        label_visibility="collapsed",
    )
    page_name = page.split(" ", 1)[1]
    st.session_state.active_page = page_name

    st.divider()
    st.caption(f"API: `{API_BASE}`")

    # Log out button (only if password protection is enabled)
    if DEMO_PASSWORD:
        st.divider()
        if st.button("Log out", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()


# ── Page routing ───────────────────────────────────────────────────────────
if page_name == "Processes":
    processes.render()
elif page_name == "Submissions":
    submissions.render()
elif page_name == "Documents":
    documents.render()
elif page_name == "Analysis":
    analysis.render()
elif page_name == "Config":
    config.render()
elif page_name == "API Keys":
    api_keys.render()
