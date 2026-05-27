"""MRI Portal PAR Downloader — Streamlit Dashboard."""

import streamlit as st

st.set_page_config(
    page_title="MRI PAR Downloader",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sidebar styling: bigger bold fonts for navigation
st.markdown("""
<style>
    [data-testid="stSidebarNav"] li a span {
        font-size: 1.15rem;
        font-weight: 700;
    }
    [data-testid="stSidebarNav"] li a {
        padding: 0.5rem 1rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("MRI Portal PAR Downloader")
st.markdown("Download Public Assessment Reports from the EU MRI Portal and extract bioequivalence data.")

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("New Run")
    st.markdown("Start a new download session. Upload a basic MRI export or search by molecule name.")
    st.page_link("pages/1_New_Run.py", label="Start New Run", icon="🔍")

with col2:
    st.subheader("Session")
    st.markdown("Monitor active pipeline runs and browse results.")
    st.page_link("pages/2_Session.py", label="View Session", icon="📊")

with col3:
    st.subheader("History")
    st.markdown("Browse all past runs. Resume failed pipelines.")
    st.page_link("pages/3_History.py", label="View History", icon="📜")

st.divider()

# Quick status summary
from mri_app.runner import list_runs

runs = list_runs()
active = [r for r in runs if r.get("running")]
completed = [r for r in runs if r.get("status", {}).get("step") == "complete"]
failed = [r for r in runs if r.get("status", {}).get("step") == "failed"]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Runs", len(runs))
m2.metric("Active", len(active))
m3.metric("Completed", len(completed))
m4.metric("Failed", len(failed))
