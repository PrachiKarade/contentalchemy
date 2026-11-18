"""Public pages shown before sign-in: landing, login and register. Plus the logout page."""

import streamlit as st

from src.web_app.auth import (
    forgot_password,
    go_to,
    log_in,
    log_out,
    register,
    update_password,
)
from src.web_app.components.theme import STATIC_DIR

FEATURES = [
    (
        ":material/travel_explore:",
        "Research & strategy",
        "Live web research turned into a cited report and a content strategy you can act on.",
    ),
    (
        ":material/article:",
        "SEO blog posts",
        "Long-form, search-optimized articles with keywords, structure and meta details.",
    ),
    (
        ":material/work:",
        "LinkedIn posts",
        "Scroll-stopping posts with hooks and hashtags, written in your brand voice.",
    ),
    (
        ":material/image:",
        "AI images",
        "On-brand visuals generated to your purpose, style and orientation.",
    ),
    (
        ":material/dashboard_customize:",
        "Multi-content campaigns",
        "Ask once, get a post, a blog and an image that share one strategy.",
    ),
    (
        ":material/verified_user:",
        "You stay in control",
        "Review, edit and approve every draft. Guardrails keep content safe and grounded.",
    ),
]

STEPS = [
    ("1", "Describe what you need", "Chat naturally, or pick a content type, tone and audience."),
    ("2", "Agents get to work", "Research, writing and image agents collaborate on your draft."),
    ("3", "Review and publish", "Approve or edit drafts, then find everything in your dashboard."),
]


def render_landing() -> None:
    with st.container(horizontal_alignment="center", gap="small"):
        st.image(str(STATIC_DIR / "logo-brand.svg"), width=300)
        st.title("Your AI content marketing team, in one chat", text_alignment="center")
        st.markdown(
            "ContentAlchemy is an AI content marketing assistant. A team of specialized agents "
            "researches your topic, plans the strategy and writes LinkedIn posts, SEO blogs and "
            "images in your brand voice, while you review and approve every piece.",
            text_alignment="center",
        )
        with st.container(horizontal=True, horizontal_alignment="center"):
            st.button(
                "Create a free account",
                type="primary",
                icon=":material/person_add:",
                on_click=go_to,
                args=("register",),
                key="landing_register",
            )
            st.button(
                "Log in",
                icon=":material/login:",
                on_click=go_to,
                args=("login",),
                key="landing_login",
            )

    st.space("medium")
    st.subheader("What you can create")
    for row_start in range(0, len(FEATURES), 3):
        columns = st.columns(3)
        for column, (icon, title, text) in zip(columns, FEATURES[row_start:row_start + 3]):
            with column.container(border=True, height="stretch"):
                st.markdown(f"#### {icon} {title}")
                st.caption(text)

    st.space("medium")
    st.subheader("How it works")
    columns = st.columns(3)
    for column, (number, title, text) in zip(columns, STEPS):
        with column.container(border=True, height="stretch"):
            st.markdown(f"**Step {number} · {title}**")
            st.caption(text)

    st.space("medium")
    st.caption("ContentAlchemy · AI Content Marketing Assistant", text_alignment="center")


def _auth_card():
    """A narrow centered column for the login and register forms."""

    _, middle, _ = st.columns([1, 1.4, 1])
    return middle.container(border=True)


def render_login() -> None:
    with _auth_card():
        st.subheader("Welcome back")
        st.caption("Log in to continue creating content.")
        with st.form("login_form", border=False):
            email = st.text_input("Email", placeholder="you@company.com", autocomplete="email", key="login_email")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")

        if submitted:
            error = log_in(email, password)
            if error:
                st.error(error)
            else:
                st.rerun()

        st.button("Forgot password?", type="tertiary", on_click=go_to, args=("forgot",), key="login_to_forgot")
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.caption("New to ContentAlchemy?")
            st.button("Create an account", type="tertiary", on_click=go_to, args=("register",), key="login_to_register")


def _back_to_login(email: str = "") -> None:
    if email:
        st.session_state["login_email"] = email
    go_to("login")


def render_forgot_password() -> None:
    with _auth_card():
        st.subheader("Reset your password")
        st.caption(
            "Enter your email and the name you registered with. You'll get a temporary password "
            "to log in with, then you'll choose a new one."
        )
        with st.form("forgot_form", border=False):
            email = st.text_input("Email", placeholder="you@company.com", autocomplete="email")
            name = st.text_input("Name", placeholder="Your registered name", autocomplete="name")
            submitted = st.form_submit_button("Get temporary password", type="primary", width="stretch")

        if submitted:
            temporary_password, error = forgot_password(email, name)
            if error:
                st.error(error)
            else:
                st.success(
                    "Copy this temporary password and use it to log in. "
                    "You'll be asked to set a new password right away.",
                    title="Your password was reset",
                )
                st.code(temporary_password, language=None)
                st.button(
                    "Log in with temporary password",
                    type="primary",
                    icon=":material/login:",
                    width="stretch",
                    on_click=_back_to_login,
                    args=(email,),
                    key="forgot_to_login",
                )
                return

        st.button("Back to log in", type="tertiary", icon=":material/arrow_back:", on_click=_back_to_login, key="forgot_back")


def render_change_password() -> None:
    """Shown only after logging in with a temporary password from "Forgot password?"."""

    with _auth_card():
        st.subheader("Choose a new password")
        st.warning(
            "You logged in with a temporary password. Set a new password to continue.",
            icon=":material/lock_reset:",
        )
        with st.form("change_password_form", border=False, clear_on_submit=True):
            current = st.text_input("Temporary password", type="password", autocomplete="current-password")
            new = st.text_input("New password", type="password", help="At least 8 characters.", autocomplete="new-password")
            confirm = st.text_input("Confirm new password", type="password", autocomplete="new-password")
            submitted = st.form_submit_button("Update password", type="primary", width="stretch")

        if submitted:
            error = update_password(current, new, confirm)
            if error:
                st.error(error)
            else:
                # Unlocks the rest of the app.
                go_to("chat")
                st.rerun()


def render_register() -> None:
    with _auth_card():
        st.subheader("Create your account")
        st.caption("Start creating content with your AI marketing team.")
        with st.form("register_form", border=False):
            name = st.text_input(
                "Name",
                placeholder="Your name",
                help="You'll need this name and your email to reset a forgotten password.",
                autocomplete="name",
            )
            email = st.text_input("Email", placeholder="you@company.com", autocomplete="email")
            password = st.text_input(
                "Password",
                type="password",
                help="At least 8 characters.",
                autocomplete="new-password",
            )
            submitted = st.form_submit_button("Create account", type="primary", width="stretch")

        if submitted:
            error = register(name, email, password)
            if error:
                st.error(error)
            else:
                st.rerun()

        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.caption("Already have an account?")
            st.button("Log in", type="tertiary", on_click=go_to, args=("login",), key="register_to_login")


def render_logout_button() -> None:
    """Log out button pinned to the right end of the header (see .st-key-logout_corner in styles.css)."""

    with st.container(key="logout_corner"):
        st.button("Log out", type="tertiary", icon=":material/logout:", on_click=log_out, key="logout_button")
