
"""ContentAlchemy Streamlit entry point.

Run from the project root:
    streamlit run src/web_app/streamlit_app.py
"""

import sys
from pathlib import Path

import streamlit as st

# Streamlit only adds this file's folder to sys.path; add the project root so `src.` imports work.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.web_app.assistant import CONTENT_TYPES  # noqa: E402
from src.web_app.components.architecture_view import render_architecture  # noqa: E402
from src.web_app.components.chat import render_chat  # noqa: E402
from src.web_app.components.content_creation import render_content  # noqa: E402
from src.web_app.components.content_dashboard import render_dashboard  # noqa: E402
from src.web_app.components.sidebar import render_sidebar  # noqa: E402
from src.web_app.components.state import init_state  # noqa: E402
from src.web_app.components.theme import apply_theme, logo_paths  # noqa: E402

st.set_page_config(page_title="ContentAlchemy", page_icon=":material/auto_awesome:", layout="wide")

init_state()

apply_theme()

logo, icon = logo_paths()

st.logo(logo, icon_image = icon, size = "large")

# The content page icon follows the type of the draft under review.
review = st.session_state.get("review")
create_icon = CONTENT_TYPES[review["type"]]["icon"] if review else ":material/description:"

pages = {
    "chat": st.Page(render_chat, title="Chat", icon=":material/forum:", url_path="chat", default=True),
    "create": st.Page(render_content, title="Content", icon=create_icon, url_path="create"),
    "dashboard": st.Page(render_dashboard, title="Content dashboard", icon=":material/dashboard:", url_path="dashboard"),
    "architecture": st.Page(render_architecture, title="Architecture", icon=":material/schema:", url_path="architecture"),
}

page = st.navigation(list(pages.values()), position="top")

render_sidebar()

# Sidebar callbacks (content type, new conversation, history) ask for a page switch.
# Switch after the sidebar renders so its widget values are kept.
target = st.session_state.pop("switch_to", None)
if target and pages[target].url_path != page.url_path:
    st.switch_page(pages[target])

page.run()
