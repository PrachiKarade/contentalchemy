
"""The app's single palette: AI purple on a soft violet background, with a dark navy sidebar.

Applied on top of the base theme in .streamlit/config.toml (keep the two in sync).
"""

from pathlib import Path

import streamlit as st

STATIC_DIR = Path(__file__).parent.parent / "static"

PALETTE = {
    # Main area: light lavender with subtle violet gradients
    "bg": (
        "radial-gradient(1200px 600px at 100% -10%, rgba(139, 92, 246, 0.16), transparent 60%), "
        "radial-gradient(900px 500px at -10% 110%, rgba(99, 102, 241, 0.12), transparent 60%), "
        "linear-gradient(180deg, #F6F3FF 0%, #F1EDFD 100%)"
    ),
    "surface": "#FFFFFF",
    "surface_hover": "#F5F1FF",
    "border": "#E4DCFA",
    "border_strong": "#C9B8F5",
    "accent": "#6D28D9",
    "accent_2": "#8B5CF6",
    "accent_soft": "#EFE8FF",
    "glow": "rgba(109, 40, 217, 0.20)",
    "text": "#1E1B3A",
    "muted": "#6B6890",
    # Sidebar: dark navy
    "nav": "linear-gradient(180deg, #0E1330 0%, #131A3F 100%)",
    "nav_text": "#E4E7F5",
    "nav_muted": "#8E95BC",
    "nav_border": "#232B57",
    "nav_hover": "rgba(139, 92, 246, 0.16)",
    "card": "#F8F6FF",
}

# Draft previews keep this height (px); longer content scrolls inside so the buttons stay in place.
DRAFT_HEIGHT = 460


def apply_theme() -> None:
    """Inject the stylesheet with the palette's CSS variables."""

    variables = "\n".join(f"    --ca-{key.replace('_', '-')}: {value};" for key, value in PALETTE.items())
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    st.html(f"<style>\n:root {{\n{variables}\n}}\n{styles}\n</style>")


def logo_paths() -> tuple[Path, Path]:
    # Mid-violet wordmark reads on both the navy sidebar and the light header.
    return STATIC_DIR / "logo-brand.svg", STATIC_DIR / "icon.svg"
