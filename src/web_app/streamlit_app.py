"""ContentAlchemy Streamlit entry point.

Signed out: landing page, login and register. Signed in: the assistant (chat, content,
dashboard, architecture) with the sidebar, plus log out.

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
from src.web_app.auth import AUTH_VIEW_KEY, is_authenticated, must_change_password  # noqa: E402
from src.web_app.components.architecture_view import render_architecture  # noqa: E402
from src.web_app.components.auth_pages import (  # noqa: E402
    render_change_password,
    render_forgot_password,
    render_landing,
    render_login,
    render_logout_button,
    render_register,
)
from src.web_app.components.chat import render_chat  # noqa: E402
from src.web_app.components.content_creation import render_content  # noqa: E402
from src.web_app.components.content_dashboard import render_dashboard  # noqa: E402
from src.web_app.components.sidebar import render_sidebar  # noqa: E402
from src.web_app.components.state import init_state  # noqa: E402
from src.web_app.components.theme import apply_theme, logo_paths  # noqa: E402

st.set_page_config(page_title="ContentAlchemy", page_icon=":material/auto_awesome:", layout="wide")

apply_theme()

logo, icon = logo_paths()
st.logo(logo, icon_image=icon, size="large")


def public_pages() -> dict:
    return {
        "home": st.Page(render_landing, title="Home", icon=":material/home:", url_path="home", default=True),
        "login": st.Page(render_login, title="Log in", icon=":material/login:", url_path="login"),
        "register": st.Page(render_register, title="Register", icon=":material/person_add:", url_path="register"),
        # Opened from the login page, not listed in the menu.
        "forgot": st.Page(
            render_forgot_password,
            title="Forgot password",
            icon=":material/lock_reset:",
            url_path="forgot-password",
            visibility="hidden",
        ),
    }


def assistant_pages() -> dict:
    # The content page icon follows the type of the draft under review.
    review = st.session_state.get("review")
    if st.session_state.get("multi") and st.session_state.get("conversation_type") == "multi":
        create_icon = CONTENT_TYPES["multi"]["icon"]
    else:
        create_icon = CONTENT_TYPES[review["type"]]["icon"] if review else ":material/description:"

    return {
        "chat": st.Page(render_chat, title="Chat", icon=":material/forum:", url_path="chat", default=True),
        "create": st.Page(render_content, title="Content", icon=create_icon, url_path="create"),
        "dashboard": st.Page(
            render_dashboard, title="Content dashboard", icon=":material/dashboard:", url_path="dashboard"
        ),
        "architecture": st.Page(
            render_architecture, title="Architecture", icon=":material/schema:", url_path="architecture"
        ),
    }


if is_authenticated() and must_change_password():
    # Logged in with a temporary password ("Forgot password?"): nothing else opens until a new
    # password is set. Change password exists only in this flow.
    pages = {
        "password": st.Page(
            render_change_password, title="Change password", icon=":material/key:", url_path="password", default=True
        )
    }
    page = st.navigation(list(pages.values()), position="top")
    render_logout_button()
    target = st.session_state.pop(AUTH_VIEW_KEY, None)
elif is_authenticated():
    init_state()
    pages = assistant_pages()
    page = st.navigation(list(pages.values()), position="top")
    render_logout_button()
    render_sidebar()
    # Sidebar callbacks (content type, new conversation, history) ask for a page switch.
    # Switch after the sidebar renders so its widget values are kept.
    target = st.session_state.pop("switch_to", None) or st.session_state.pop(AUTH_VIEW_KEY, None)
else:
    pages = public_pages()
    page = st.navigation(list(pages.values()), position="top")
    target = st.session_state.pop(AUTH_VIEW_KEY, None)

if target in pages and pages[target].url_path != page.url_path:
    st.switch_page(pages[target])

page.run()
