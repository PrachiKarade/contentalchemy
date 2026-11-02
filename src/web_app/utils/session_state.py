
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROFILE_PATH = PROJECT_ROOT / "inputs" / "user_profile.md"

QUESTION_LABELS = {
    "identity": "Who are you?",
    "role": "Title or role",
    "objective": "LinkedIn objective",
    "experience": "Experience level",
    "tone": "Preferred tone",
}


def save_profile_markdown(answers: dict) -> Path:
    lines = ["# LinkedIn User Profile", ""]

    for key, label in QUESTION_LABELS.items():
        answer = answers[key]

        lines.extend([f"## {label}", ""])

        for option in answer["selected"]:
            lines.append(f"- {option}")

        if answer["other_text"]:
            lines.append(f"- Other: {answer['other_text']}")

        lines.append("")

    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text( "\n".join(lines), encoding="utf-8", )

    return PROFILE_PATH


def read_profile_text() -> str:
    """Return the saved profile markdown, or an empty string if there is none."""

    return PROFILE_PATH.read_text(encoding="utf-8") if PROFILE_PATH.exists() else ""


def load_profile_markdown() -> dict | None:
    """Parse the saved profile back into the questionnaire answers format."""

    text = read_profile_text()
    if not text:
        return None

    keys_by_label = {label: key for key, label in QUESTION_LABELS.items()}
    answers = {key: {"selected": [], "other_text": ""} for key in QUESTION_LABELS}
    current = None

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("## "):
            current = keys_by_label.get(line[3:].strip())
        elif current and line.startswith("- "):
            value = line[2:].strip()
            if value.startswith("Other:"):
                answers[current]["other_text"] = value[len("Other:"):].strip()
            else:
                answers[current]["selected"].append(value)

    if not all(answer["selected"] or answer["other_text"] for answer in answers.values()):
        return None

    return answers
