"""Collect the image generator's preferences: purpose, style, orientation and quality.

image_request_analyzer_node reads the preferences the user already gave in
their request. image_preference_interaction_node then asks for each missing
one, one question per run (like the LinkedIn profile questions), and the
workflow loops back to it until nothing is missing.

Each question is a separate node run, so resuming never replays earlier
questions or the LLM extraction.
"""

import json
import re

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.integrations.openai_client import generate_text
from src.prompts.image_generator_prompt import IMAGE_PREFERENCE_EXTRACTION_SYSTEM

logger = setup_logger("image_preferences")

IMAGE_PREFERENCE_QUESTIONS = [
    {
        "key": "image_purpose",
        "question": "What will you use this image for?",
        "options": ["Blog article", "LinkedIn post", "Website", "Presentation", "Marketing campaign", "Other"],
    },
    {
        "key": "image_visual_style",
        "question": "What visual style would you like?",
        "options": ["Photorealistic", "3D illustration", "Minimalist", "Cinematic", "Vector art", "Watercolor", "Other"],
    },
    {
        "key": "image_orientation",
        "question": "Which orientation do you prefer?",
        "options": ["Square", "Portrait", "Landscape"],
    },
    {
        "key": "image_quality",
        "question": "Which image quality do you prefer?",
        "options": ["Standard", "HD"],
    },
]

QUESTIONS_BY_KEY = {question["key"]: question for question in IMAGE_PREFERENCE_QUESTIONS}

# Words that map free text to the values DALL-E 3 accepts.
ORIENTATION_WORDS = {
    "square": ["square", "1:1", "instagram"],
    "portrait": ["portrait", "vertical", "tall", "story", "9:16"],
    "landscape": ["landscape", "horizontal", "wide", "banner", "16:9"],
}
QUALITY_WORDS = {
    "hd": ["hd", "high", "detailed", "best", "premium"],
    "standard": ["standard", "normal", "regular", "default", "basic"],
}

# --------------------------------------------------------------------------
# method:  for matching words in a text to a set of values
# --------------------------------------------------------------------------

def _match_words(text: str, words_by_value: dict[str, list[str]]) -> str | None:
    text = text.strip().lower()
    for value, words in words_by_value.items():
        if any(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) for word in words):
            return value
    return None

# --------------------------------------------------------------------------
# method:  for normalizing a preference value
# --------------------------------------------------------------------------

def normalize_preference(key: str, value) -> str | None:
    """Clean an answer; None if it is empty or not a valid value for the field."""

    if not isinstance(value, str) or not value.strip():
        return None
    if key == "image_orientation":
        return _match_words(value, ORIENTATION_WORDS)
    if key == "image_quality":
        return _match_words(value, QUALITY_WORDS)
    return value.strip()

# --------------------------------------------------------------------------
# method:  for checking which image preferences are still missing
# --------------------------------------------------------------------------
def missing_image_preferences(state: ContentState) -> list[str]:
    return [question["key"] for question in IMAGE_PREFERENCE_QUESTIONS if not state.get(question["key"])]

# --------------------------------------------------------------------------
# method:  for routing to the next node based on missing image preferences
# --------------------------------------------------------------------------

def route_image_preferences(state: ContentState) -> str:
    missing = missing_image_preferences(state)

    logger.info( "Image preferences remaining: %s", missing, )

    if missing:
        return "ask"

    return "generate"

# --------------------------------------------------------------------------
# method:  for extracting image preferences from user request
# --------------------------------------------------------------------------
def extract_image_preferences(user_request: str) -> dict:
    """Preferences the user stated in their request. Missing ones are left out."""

    try:
        raw_output = generate_text(
            query=f"USER REQUEST:\n{user_request.strip()}",
            system_prompt=IMAGE_PREFERENCE_EXTRACTION_SYSTEM,
            max_output_tokens=200,
        )
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_output.strip(), flags=re.IGNORECASE).strip()
        data = json.loads(cleaned)
    except Exception:
        # Not fatal: the user is simply asked for every preference.
        logger.exception("Could not extract image preferences from the request.")
        return {}

    if not isinstance(data, dict):
        return {}

    found = {}
    for key in QUESTIONS_BY_KEY:
        value = normalize_preference(key, data.get(key))
        if value:
            found[key] = value
    return found


# --------------------------------------------------------------------------
# method:  for generating an image using Google Gemini Image
# --------------------------------------------------------------------------

def image_request_analyzer_node(state: ContentState) -> dict:
    """Read the image preferences already given in the user's request."""

    get_stream_writer()({"event": "status", "text": "Reading your image request..."})

    found = extract_image_preferences(state.get("user_request", ""))
    # Preferences already in state (set by the user explicitly) win.
    updates = {key: value for key, value in found.items() if not state.get(key)}

    logger.info(
        "Image preferences from the request: %s; still missing: %s",
        list(updates),
        [key for key in missing_image_preferences({**state, **updates})],
    )
    return {**updates, "image_preference_error": "", "current_agent": "image_request_analyzer"}



# --------------------------------------------------------------------------
# method:  for asking the user for the next missing image preference
# --------------------------------------------------------------------------
def image_preference_interaction_node(state: ContentState) -> dict:
    """Ask for the next missing image preference."""

    missing = missing_image_preferences(state)
    if not missing:
        return {}

    question = QUESTIONS_BY_KEY[missing[0]]
    error = state.get("image_preference_error", "")

    response = interrupt({
        "interaction_type": "image_preference_question",
        "agent": "image_generator",
        "lookup_key": question["key"],
        "question": f"{error} {question['question']}".strip(),
        "options": question["options"],
        "selection_type": "single",
        "allow_other": "Other" in question["options"],
        # The UI shows "Generate image" instead of "Next question" on the last one.
        "is_last": len(missing) == 1,
    })

    if not isinstance(response, dict):
        raise ValueError("The image preference answer must be a dictionary.")

    selected = response.get("selected_options") or []
    if isinstance(selected, str):
        selected = [selected]
    answers = [option for option in selected if option != "Other"]
    if (response.get("other_text") or "").strip():
        answers.append(response["other_text"].strip())

    value = normalize_preference(question["key"], answers[0] if answers else "")
    if not value:
        # Ask the same question again, explaining why.
        choices = ", ".join(option for option in question["options"] if option != "Other")
        logger.info("Invalid answer for %s: %s", question["key"], answers)
        return {"image_preference_error": f"Please choose one of: {choices}."}

    logger.info("Image preference %s = %s", question["key"], value)
    return {question["key"]: value, "image_preference_error": "", "current_agent": "image_preference_interaction"}
