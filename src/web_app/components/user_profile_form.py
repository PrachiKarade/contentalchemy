import streamlit as st

from src.core.logger import setup_logger
from src.web_app.utils.session_state import save_profile_markdown

logger = setup_logger(__name__)

OTHER = "Other"

QUESTIONS = [
    {
        "key": "identity",
        "question": "Who are you?",
        "icon": ":material/person:",
        "multi": False,
        "options": [
            "Software Engineer",
            "Tech Professional",
            "Founder / Entrepreneur",
            "Business Owner",
            "Consultant",
            "Content Creator",
            "Student",
            OTHER,
        ],
    },
    {
        "key": "role",
        "question": "What is your title or role?",
        "icon": ":material/badge:",
        "multi": False,
        "options": [
            "Software Engineer",
            "Senior Engineer",
            "Tech Lead",
            "Engineering Manager",
            "Director / Executive",
            "Founder",
            "Consultant",
            OTHER,
        ],
    },
    {
        "key": "objective",
        "question": "What is your main objective on LinkedIn?",
        "icon": ":material/flag:",
        "multi": True,
        "options": [
            "Build Personal Brand",
            "Find a Job",
            "Grow My Network",
            "Share Knowledge",
            "Generate Leads",
            "Promote My Business",
            OTHER,
        ],
    },
    {
        "key": "experience",
        "question": "What is your experience level?",
        "icon": ":material/timeline:",
        "multi": False,
        "options": [
            "Student / Entry Level",
            "1–3 Years",
            "4–7 Years",
            "8–12 Years",
            "12+ Years",
            OTHER,
        ],
    },
    {
        "key": "tone",
        "question": "What tone do you prefer?",
        "icon": ":material/record_voice_over:",
        "multi": True,
        "options": [
            "Professional",
            "Conversational",
            "Friendly",
            "Thought Leadership",
            "Inspirational",
            "Humorous",
            OTHER,
        ],
    },
]


def render_question(number: int, item: dict) -> dict:
    """Render one question card and return its answer."""

    key = item["key"]

    with st.container(border=True, key=f"linkedin_card_{key}"):
        st.markdown(f"{item['icon']} **{number}. {item['question']}**")
        st.caption("Select all that apply" if item["multi"] else "Choose one")

        value = st.pills(
            item["question"],
            options=item["options"],
            selection_mode="multi" if item["multi"] else "single",
            key=f"linkedin_{key}",
            label_visibility="collapsed",
        )
        selected = list(value or []) if item["multi"] else [value] if value else []

        other_text = ""
        if OTHER in selected:
            other_text = st.text_input(
                "Your answer",
                placeholder="Type your own answer",
                key=f"linkedin_{key}_other",
                label_visibility="collapsed",
            ).strip()

    return {
        "selected": [option for option in selected if option != OTHER],
        "other_text": other_text,
    }


def is_answered(answer: dict) -> bool:
    return bool(answer["selected"] or answer["other_text"])


def prefill_profile_form(answers: dict) -> None:
    """Load saved answers into the form widgets so the user can edit them."""

    for item in QUESTIONS:
        key = item["key"]
        answer = answers[key]
        selected = [option for option in answer["selected"] if option in item["options"]]
        if answer["other_text"]:
            selected.append(OTHER)
            st.session_state[f"linkedin_{key}_other"] = answer["other_text"]

        if item["multi"]:
            st.session_state[f"linkedin_{key}"] = selected
        else:
            st.session_state[f"linkedin_{key}"] = selected[0] if selected else None


def render_user_profile_form(on_cancel=None):
    """Render the questionnaire. Pass on_cancel to show a Cancel button while editing."""

    with st.container(border=True, key="linkedin_profile_form"):
        st.subheader(":material/work: Personalize your LinkedIn content", anchor=False)
        st.caption(
            "Answer five quick questions so the assistant can write LinkedIn posts "
            "that match your profile and goals."
        )

        progress = st.empty()

        answers = {
            item["key"]: render_question(number, item)
            for number, item in enumerate(QUESTIONS, start=1)
        }

        answered = sum(is_answered(answer) for answer in answers.values())
        progress.progress(
            answered / len(QUESTIONS),
            text=f"{answered} of {len(QUESTIONS)} answered",
        )

        with st.container(horizontal=True):
            if on_cancel:
                st.button(
                    "Cancel",
                    icon=":material/close:",
                    key="cancel_linkedin_profile",
                    on_click=on_cancel,
                )
            save = st.button(
                "Save profile and continue",
                type="primary",
                icon=":material/check_circle:",
                width="stretch",
                key="save_linkedin_profile",
            )

        if not save:
            return None

        if answered < len(QUESTIONS):
            st.error(
                "If you pick Other, type your answer in the box.",
                title="Please answer all five questions",
                icon=":material/error:",
            )
            return None

        try:
            save_profile_markdown(answers)
        except Exception:
            logger.exception("Failed to save LinkedIn profile")
            st.error("Could not save your profile. Please try again.", icon=":material/error:")
            return None

        st.session_state["linkedin_profile"] = answers
        st.session_state["linkedin_profile_completed"] = True
        logger.info("LinkedIn profile questionnaire completed")

        st.toast("Profile saved", icon=":material/check_circle:")
        st.rerun()
