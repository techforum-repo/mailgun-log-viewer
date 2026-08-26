from __future__ import annotations

import streamlit as st

from mailgun_log_viewer.config import harden_env_file
from mailgun_log_viewer.ui import diagnostics_page, events_page, settings_page
from mailgun_log_viewer.ui.shared import CUSTOM_CSS, init_session_state, render_hero, render_sidebar

harden_env_file()
st.set_page_config(page_title="Mailgun Log Viewer", page_icon="📬", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

init_session_state()
page = render_sidebar()
render_hero()

PAGES = {
    "Events": events_page.render,
    "Settings": settings_page.render,
    "Diagnostics": diagnostics_page.render,
}
PAGES[page]()
