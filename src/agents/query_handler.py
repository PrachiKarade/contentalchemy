
import json
import re
from typing import Literal, TypedDict

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.integrations.text_provider_manager import text_provider_manager


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


VALID_INTENTS = {
    "research",
    "blog",
    "linkedin",
    "image",
    "strategy",
    "multi",
}

# ----------------------------------------------------
# Query Handler Logic
# ----------------------------------------------------

def analyze_query( user_request: str ) -> QueryAnalysis:
        """Classify a content request and extract its key details."""

        if not user_request or not user_request.strip():
            raise ValueError("User request cannot be empty.")

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
        "objective": "what the user wants to achieve"
        }

        Intent selection:
        - research: The user primarily wants information or research.
        - blog: The user wants an SEO blog or article.
        - linkedin: The user wants a LinkedIn post.
        - image: The user primarily wants an image or visual.
        - strategy: The user wants a content plan or marketing strategy.
        - multi: The user explicitly requests multiple deliverables,
        such as research AND a blog AND a social media post.

        Rules:
        - Use the user's explicit request to determine intent.
        - Do not choose multi merely because research could help create content.
        - Do not invent user preferences or claim missing details were supplied.
        - If audience or tone is unspecified, use reasonable defaults.
        - Return keywords as a JSON array of strings.
        """

        user_prompt = f"""
        USER REQUEST: {user_request.strip()}

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

        if data.get("intent") not in VALID_INTENTS:
            raise ValueError( f"Unsupported intent: {data.get('intent')!r}"  )

        for field in ("topic", "target_audience", "tone", "objective"):
            if not isinstance(data.get(field), str):
                raise ValueError(f"Invalid or missing field: {field}")

        if not data["topic"].strip():
            raise ValueError("Query Handler did not identify a topic.")

        if not isinstance(data.get("keywords"), list) or not all(
            isinstance(item, str) for item in data["keywords"]
        ):
            raise ValueError("Keywords must be a list of strings.")

        result: QueryAnalysis = {
            "intent": data["intent"],
            "topic":  data["topic"].strip(),
            "target_audience": data["target_audience"].strip(),
            "tone":      data["tone"].strip(),
            "keywords":  data["keywords"],
            "objective": data["objective"].strip(),
        }

        logger.info("Detected intent: %s", result["intent"])

        return result

# ----------------------------------------------------
# Query Handler Agent Node
# ----------------------------------------------------

def query_handler_node(state: ContentState) -> dict:
    """Analyze the request and return updates for LangGraph state."""

    logger.info("Analyzing user request")

    analysis = analyze_query(
        user_request = state["user_request"]        
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
    }

    logger.info(
        "Query analyzed: intent=%s, topic=%s",
        updates["intent"],
        analysis["topic"],
    )

    return updates
