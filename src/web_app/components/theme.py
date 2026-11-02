
"""Theme picker and color palettes applied on top of the base theme in .streamlit/config.toml."""

from pathlib import Path

import streamlit as st

STATIC_DIR = Path(__file__).parent.parent / "static"

# Plain labels because bind="query-params" writes the displayed label to the URL (?theme_mode=Light).
MODES = ["Dark", "Light"]

# Only Classic has a dark variant; the colorful palettes are light-only.
THEMES = {
    "Classic": {
        "dark": {
            "bg": "#000000",
            "sidebar": "rgba(10, 10, 10, 0.95)",
            "surface": "rgba(255, 255, 255, 0.05)",
            "border": "rgba(255, 255, 255, 0.14)",
            "accent": "#FAFAFA",
            "accent_2": "#A1A1AA",
            "glow": "rgba(255, 255, 255, 0.12)",
            "on_accent": "#000000",
            "popover": "#0A0A0A",
        },
        "light": {
            "bg": "#FFFFFF",
            "sidebar": "rgba(250, 250, 250, 0.95)",
            "surface": "#FFFFFF",
            "border": "rgba(0, 0, 0, 0.12)",
            "accent": "#111111",
            "accent_2": "#52525B",
            "glow": "rgba(0, 0, 0, 0.08)",
            "text": "#0A0A0A",
            "muted": "#6B7280",
        },
    },
    "Ocean": {
        "light": {
            "bg": "linear-gradient(135deg, #E3F6FF 0%, #DDFBF4 50%, #CDEBFF 100%)",
            "sidebar": "rgba(255, 255, 255, 0.6)",
            "surface": "rgba(255, 255, 255, 0.75)",
            "border": "rgba(13, 148, 136, 0.3)",
            "accent": "#0D9488",
            "accent_2": "#0284C7",
            "glow": "rgba(13, 148, 136, 0.25)",
            "text": "#082F49",
            "muted": "#3E5C70",
        },
    },
    "Sunset": {
        "light": {
            "bg": "linear-gradient(135deg, #FFF0E3 0%, #FFE2EC 55%, #FFD3CC 100%)",
            "sidebar": "rgba(255, 255, 255, 0.6)",
            "surface": "rgba(255, 255, 255, 0.75)",
            "border": "rgba(234, 88, 12, 0.3)",
            "accent": "#EA580C",
            "accent_2": "#DB2777",
            "glow": "rgba(234, 88, 12, 0.25)",
            "text": "#3B0A1E",
            "muted": "#7A4A55",
        },
    },
    "Neon": {
        "light": {
            "bg": "linear-gradient(135deg, #F4FEDF 0%, #F3F0FF 60%, #FCEEFF 100%)",
            "sidebar": "rgba(255, 255, 255, 0.6)",
            "surface": "rgba(255, 255, 255, 0.75)",
            "border": "rgba(101, 163, 13, 0.35)",
            "accent": "#4D7C0F",
            "accent_2": "#C026D3",
            "glow": "rgba(101, 163, 13, 0.25)",
            "text": "#1A1A2E",
            "muted": "#555570",
        },
    },
    "Emerald": {
        "light": {
            "bg": "linear-gradient(135deg, #E8FCF2 0%, #E2FBF7 55%, #FDFAE1 100%)",
            "sidebar": "rgba(255, 255, 255, 0.6)",
            "surface": "rgba(255, 255, 255, 0.75)",
            "border": "rgba(5, 150, 105, 0.3)",
            "accent": "#047857",
            "accent_2": "#CA8A04",
            "glow": "rgba(5, 150, 105, 0.25)",
            "text": "#052E2B",
            "muted": "#3F625C",
        },
    },
}

# Draft previews keep this height (px); longer content scrolls inside so the buttons stay in place.
DRAFT_HEIGHT = 460

DEFAULT_MODE = "Light"
DEFAULT_THEME = "Ocean"


def render_theme_picker() -> tuple[str, str]:
    """Palette button pinned to the top-right corner. Returns (mode, theme name)."""

    with st.container(key="theme_picker", width="content"):
        with st.popover("", icon=":material/palette:", type="tertiary", help="Theme"):
            theme = st.pills(
                "Color",
                list(THEMES),
                default=DEFAULT_THEME,
                required=True,
                key="theme_color",
                bind="query-params",
            ) or DEFAULT_THEME

            # The mode switch only appears for palettes that have a dark variant.
            if "dark" not in THEMES[theme]:
                return "light", theme

            mode = st.segmented_control(
                "Mode",
                MODES,
                default=DEFAULT_MODE,
                required=True,
                key="theme_mode",
                bind="query-params",
            )
    return (mode or DEFAULT_MODE).lower(), theme


def apply_theme(mode: str, theme: str) -> None:
    """Inject the stylesheet with the chosen palette's CSS variables."""

    variants = THEMES.get(theme, THEMES[DEFAULT_THEME])
    if mode not in variants:
        mode = "light"
    palette = variants[mode]
    variables = "\n".join(
        f"    --ca-{key.replace('_', '-')}: {value};" for key, value in palette.items()
    )
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    if mode == "light":
        styles += (STATIC_DIR / "light.css").read_text(encoding="utf-8")
    st.html(f"<style>\n:root {{\n{variables}\n}}\n{styles}\n</style>")


def logo_paths(mode: str) -> tuple[Path, Path]:
    logo = "logo-light.svg" if mode == "light" else "logo.svg"
    return STATIC_DIR / logo, STATIC_DIR / "icon.svg"
