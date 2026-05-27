"""
Doc-I — Document Intelligence Platform
Streamlit Demo Application

Entry point — sidebar navigation and page routing only.
Each page lives in pages/ as a standalone module.
"""

import streamlit as st

from api_client import check_api_health
from constants import API_BASE
from views import analysis, config, documents, processes, submissions

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Doc-I — Document Intelligence",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ─────────────────────────────────────────────────
for key, value in {
    "selected_process_id": None,
    "selected_submission_id": None,
    "active_page": "Processes",
    "categories_cache": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/document.png", width=60)
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

    PAGES = ["🏠 Processes", "📋 Submissions", "📄 Documents", "🔍 Analysis", "⚙️ Config"]
    ICON_MAP = {"Processes": "🏠", "Submissions": "📋", "Documents": "📄", "Analysis": "🔍", "Config": "⚙️"}

    current = f"{ICON_MAP[st.session_state.active_page]} {st.session_state.active_page}"

    page = st.radio(
        "Navigate",
        PAGES,
        index=PAGES.index(current),
        label_visibility="collapsed",
    )
    page_name = page.split(" ", 1)[1]
    st.session_state.active_page = page_name

    st.divider()
    st.caption(f"API: `{API_BASE}`")


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
