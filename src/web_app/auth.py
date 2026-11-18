"""Sign-in session for the web app, backed by src/repositories/user_repository.py.

The authenticated user's ID lives in st.session_state["user_id"] (the username is kept
next to it for display). Logging out clears the whole session.
"""

import streamlit as st

from src.core.logger import setup_logger
from src.repositories.user_repository import (
    authenticate_user,
    change_password,
    create_user,
    ensure_user_indexes,
    reset_password_to_temporary,
)

logger = setup_logger("web_auth")

# Page the entry point should switch to on the next run ("home", "login", "register", "chat").
AUTH_VIEW_KEY = "auth_view"

DATABASE_ERROR = "We couldn't reach the user database. Please try again in a moment."


@st.cache_resource(show_spinner=False)
def _prepare_users_collection() -> bool:
    # Raising is not cached, so a failed attempt is retried on the next login or registration.
    ensure_user_indexes()
    return True


def prepare_users_collection() -> None:
    """Create the unique email index once per server process."""

    try:
        _prepare_users_collection()
    except Exception:
        logger.exception("Could not create the users collection indexes")


def is_authenticated() -> bool:
    return bool(st.session_state.get("user_id"))


def go_to(view: str) -> None:
    """Ask the entry point to open another page (use as a button callback)."""

    st.session_state[AUTH_VIEW_KEY] = view


def must_change_password() -> bool:
    """True after logging in with a temporary password, until a new one is set."""

    return bool(st.session_state.get("must_change_password"))


def _start_session(user: dict) -> None:
    st.session_state["user_id"] = user["user_id"]
    st.session_state["username"] = user.get("username") or "there"
    st.session_state["must_change_password"] = bool(user.get("must_change_password"))
    go_to("password" if must_change_password() else "chat")


def log_in(email: str, password: str) -> str | None:
    """Sign the user in. Returns an error message, or None on success."""

    if not email.strip() or not password:
        return "Enter your email and password."

    prepare_users_collection()
    try:
        user = authenticate_user(email, password)
    except Exception:
        logger.exception("Login failed because of a database error")
        return DATABASE_ERROR

    if not user:
        return "Incorrect email or password."

    _start_session(user)
    logger.info("User logged in: %s", user["user_id"])
    return None


def register(name: str, email: str, password: str) -> str | None:
    """Create the account and sign the new user in. Returns an error message, or None on success."""

    prepare_users_collection()
    try:
        user = create_user(username=name, email=email, password=password)
    except ValueError as error:
        # Validation messages from the repository are written for the user.
        return str(error)
    except Exception:
        logger.exception("Registration failed because of a database error")
        return DATABASE_ERROR

    if not user:
        return DATABASE_ERROR

    _start_session(user)
    return None


def forgot_password(email: str, name: str) -> tuple[str | None, str | None]:
    """Issue a temporary password. Returns (temporary_password, error)."""

    if not email.strip() or not name.strip():
        return None, "Enter the email and the name you registered with."

    try:
        temporary_password = reset_password_to_temporary(email, name)
    except Exception:
        logger.exception("Password reset failed because of a database error")
        return None, DATABASE_ERROR

    if not temporary_password:
        return None, "No account matches that email and name."

    return temporary_password, None


def update_password(current_password: str, new_password: str, confirm_password: str) -> str | None:
    """Change the signed-in user's password. Returns an error message, or None on success."""

    if new_password != confirm_password:
        return "The new passwords don't match."

    try:
        change_password(st.session_state["user_id"], current_password, new_password)
    except ValueError as error:
        return str(error)
    except Exception:
        logger.exception("Password change failed because of a database error")
        return DATABASE_ERROR

    st.session_state["must_change_password"] = False
    return None


def log_out() -> None:
    """Clear the session and send the user back to the login page."""

    user_id = st.session_state.get("user_id")
    st.session_state.clear()
    go_to("login")
    logger.info("User logged out: %s", user_id)
