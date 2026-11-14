
import json
import re
from typing import Literal, TypedDict

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.integrations.text_provider_manager import text_provider_manager
from src.guardrails.input_guardrails import (
    UserRequestInput,
    QueryAnalysisOutput,
)


logger = setup_logger("query_handler")


ContentIntent = Literal[
    "research",
    "blog",
    "linkedin",
    "image",
    "strategy",
    "multi",
]


class QueryAnalysis(TypedDict):
    intent: ContentIntent
    topic: str
    target_audience: str
    tone: str
    keywords: list[str]
    objective: str
    requested_agents: list[str]


# ----------------------------------------------------
# Query Handler Logic
# ----------------------------------------------------

def analyze_query(user_request: str) -> QueryAnalysis:
    """Classify a content request and extract its key details."""

    validated_input = UserRequestInput(user_request=user_request)
    user_request = validated_input.user_request

    system_prompt = """
    You are the Query Handler for ContentAlchemy, an AI content
    marketing assistant.

    Analyze the user's request and return ONLY a valid JSON object
    with these exact fields:

    {
        "intent": "research | blog | linkedin | image | strategy | multi",
        "topic": "main topic",
        "target_audience": "intended audience",
        "tone": "desired tone",
        "keywords": ["keyword1", "keyword2"],
        "objective": "what the user wants to achieve",
        "requested_agents": ["research", "blog", "linkedin", "image", "strategy"]
    }

    Intent selection:
    - research: Primarily research or information.
    - blog: SEO blog or article.
    - linkedin: LinkedIn post.
    - image: Image or visual.
    - strategy: Content plan or marketing strategy.
    - multi: Explicitly requests two or more deliverables.

    Requested agents:
    - Include only deliverables explicitly requested by the user.
    - Valid values: research, blog, linkedin, image, strategy.
    - Include multiple values when multiple deliverables are requested.
    - Do not include research just because it is needed internally
      to generate a blog or LinkedIn post.
    - Do not include an agent merely because its output could be useful.
    - For a single deliverable, return a list containing one value.
    - Do not return duplicate values.

    Additional rules:
    - Use the user's explicit request to determine intent.
    - Do not choose multi merely because research could help create content.
    - Do not invent user preferences.
    - If audience or tone is unspecified, use reasonable defaults.
    - Return keywords as a JSON array of strings.
    """

    user_prompt = f"""
    USER REQUEST: {user_request}

    Classify the request and extract its details.
    """

    logger.info("Analyzing user request")

    raw_output = text_provider_manager.generate_text(
        query=user_prompt,
        system_prompt=system_prompt,
        max_output_tokens=700,
    )

    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        raw_output.strip(),
        flags=re.IGNORECASE,
    ).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Query Handler returned invalid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("Query Handler output must be a JSON object.")

    validated_output = QueryAnalysisOutput.model_validate(data)

    result: QueryAnalysis = validated_output.model_dump()

    logger.info(
        "Detected intent: %s | Requested agents: %s",
        result["intent"],
        result["requested_agents"],
    )

    return result


# ----------------------------------------------------
# Query Handler Agent Node
# ----------------------------------------------------

def query_handler_node(state: ContentState) -> dict:
    """Analyze the request and return updates for LangGraph state."""

    logger.info("Analyzing user request")

    analysis = analyze_query(
        user_request=state["user_request"]
    )

    # Explicit user-selected settings take priority over AI analysis.
    updates = {
        "intent": state.get("intent") or analysis["intent"],
        "topic": analysis["topic"],
        "target_audience": (
            state.get("target_audience") or analysis["target_audience"]
        ),
        "tone": state.get("tone") or analysis["tone"],
        "keywords": state.get("keywords") or analysis["keywords"],
        "objective": state.get("objective") or analysis["objective"],
        "requested_agents": (
            state.get("requested_agents") or analysis["requested_agents"]
        ),
    }

    logger.info(
        "Query analyzed: intent=%s, topic=%s, requested_agents=%s",
        updates["intent"],
        analysis["topic"],
        updates["requested_agents"],
    )

    return updates

# ---------------------------
# test 
# --------------------------------


