
import json
import re
from typing import TypedDict

from src.core.logger import setup_logger
from src.integrations.openai_client import generate_text
from src.core.state import ContentState
from langchain_core.messages import AIMessage
from src.repositories.conversation_repository import get_conversation
from src.repositories.message_repository import add_message
from src.prompts.linkedin_agent_prompt import get_linkedin_system_prompt


logger = setup_logger("linkedin_writer")


class LinkedInDraft(TypedDict):
    hook: str
    post_body: str
    hashtags: list[str]
    call_to_action: str


def write_linkedin_post(
    topic: str,
    profile_answers: dict,
    target_audience: str = "",
    tone: str = "Professional",
    keywords: list[str] | None = None,
    objective: str = "",
) -> LinkedInDraft:
    """
    Generate a structured LinkedIn post using the user's profile
    and content requirements.
    """

    if not topic or not topic.strip():
        raise ValueError("Topic cannot be empty.")
   
    keywords = keywords or []

    system_prompt = get_linkedin_system_prompt()

    user_prompt = f"""
                Create a LinkedIn post using the following information.

                USER PROFESSIONAL PROFILE
                - Professional identity: {", ".join(profile_answers.get("professional_identity", []))}
                - Current role: {", ".join(profile_answers.get("current_role", []))}
                - Experience level: {", ".join(profile_answers.get("experience_level", []))}

                TOPIC:{topic.strip()}

                TARGET AUDIENCE: {target_audience or "Infer the most relevant professional audience"}

                PREFERRED TONE: {tone}

                CONTENT OBJECTIVE: {objective or "Provide value and encourage meaningful engagement"}

                TARGET KEYWORDS:{", ".join(keywords) if keywords else "Use relevant keywords naturally"}
                Create content that:
                1. Reflects the user's professional identity and experience.
                2. Aligns with their LinkedIn objective.
                3. Uses their preferred tone.
                4. Provides useful and engaging information about the topic.
                5. Sounds authentic and natural, not like generic AI-generated content.

                Generate exactly ONE LinkedIn post.
                Return the requested structured JSON object.
                """

    logger.info("Generating LinkedIn draft for topic: %s", topic)

    raw_output = generate_text(
        query = user_prompt,
        system_prompt = system_prompt,
        max_output_tokens =1600,
    )

    # Handle JSON wrapped in Markdown fences, if returned by the model.
    cleaned_output = raw_output.strip()

    cleaned_output = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        cleaned_output,
        flags=re.IGNORECASE,
    ).strip()

    try:
        data = json.loads(cleaned_output)
    except json.JSONDecodeError as exc:
        logger.exception("Could not parse LinkedIn writer output as JSON")
        raise ValueError( "The LinkedIn Writer returned invalid JSON. Please retry." ) from exc

    required_keys = {
        "hook",
        "post_body",
        "hashtags",
        "call_to_action",
    }

    if not isinstance(data, dict) or not required_keys.issubset(data):
        raise ValueError( "LinkedIn Writer output is missing required fields." )

    if not all(
        isinstance(data[key], str) and data[key].strip()
        for key in ("hook", "post_body", "call_to_action")
    ):
        raise ValueError( "Hook, post body, and call to action must be non-empty strings.")

    if not isinstance(data["hashtags"], list) or not all(
        isinstance(tag, str) for tag in data["hashtags"]
    ):
        raise ValueError("Hashtags must be a list of strings.")

    # Normalize hashtags and remove empty entries.
    hashtags = []
    for tag in data["hashtags"]:
        tag = tag.strip().lstrip("#")
        if tag:
            hashtags.append(f"#{tag}")

    draft: LinkedInDraft = {
        "hook": data["hook"].strip(),
        "post_body": data["post_body"].strip(),
        "hashtags": hashtags,
        "call_to_action": data["call_to_action"].strip(),
    }

    logger.info("LinkedIn draft generated successfully")
    return draft

def linkedin_writer_node(state: ContentState) -> dict:
    """Generate a LinkedIn post using the conversation and its profile."""

    user_id         = state.get("user_id", "").strip()
    conversation_id = state.get("conversation_id", "").strip()

    if not user_id:
        raise ValueError( "user_id is required to generate a LinkedIn post."  )

    if not conversation_id:
        raise ValueError("conversation_id is required to generate a LinkedIn post." )

    logger.info( "Generating LinkedIn post for conversation %s",  conversation_id, )

    # 1. Load the conversation and verify ownership.
    conversation = get_conversation( conversation_id=conversation_id, user_id=user_id, )

    if conversation is None:
        raise ValueError( "Conversation was not found for this user.")

    if conversation.get("content_type") != "linkedin":
        raise ValueError("linkedin_writer_node only supports LinkedIn conversations." )
    
    # 2. Load the Markdown profile for this exact conversation.
    #profile = get_profile( user_id = user_id, conversation_id = conversation_id, )
    profile_answers = state.get("linkedin_profile_answers", {})

    #profile_markdown = profile.get("profile_markdown", "").strip()
    # 3. Use state values when available; otherwise use saved
    #    conversation settings.
    topic = state.get("topic") or conversation.get("topic", "")
    target_audience = (
        state.get("target_audience")
        or conversation.get("target_audience", "")
    )
    tone = (
        state.get("tone")
        or conversation.get("tone")
        or "Professional"
    )
    keywords = (
        state.get("keywords")
        if state.get("keywords") is not None
        else conversation.get("keywords", [])
    )
    objective = (
        state.get("objective")
        or conversation.get("objective", "")
    )

    if not topic.strip():
        raise ValueError( "A topic is required to generate a LinkedIn post." )

     # 4. Generate the structured LinkedIn draft.
    draft = write_linkedin_post(
        topic=topic,
        profile_answers=profile_answers,
        target_audience=target_audience,
        tone=tone,
        keywords=keywords,
        objective=objective,
    )

    # The reviewer sees the whole post, not only the body.
    full_post = "\n\n".join([
        draft["hook"],
        draft["post_body"],
        draft["call_to_action"],
        " ".join(draft["hashtags"]),
    ]).strip()

    # 5. Save generated content in MongoDB.
    generated_message = add_message(
    conversation_id=conversation_id,
    user_id=user_id,
    role="assistant",
    message_type="generated_content",
    content_type="linkedin",
    content=draft,
    agent_name="linkedin_writer",
    metadata={
        "status": "draft",
        "version": 1,
        "content_text": full_post,
    },
)

    generated_content_message_id = generated_message["message_id"]

    completed_agents = list(state.get("completed_agents", []))

    if "linkedin_writer" not in completed_agents:
        completed_agents.append("linkedin_writer")

    logger.info(
        "LinkedIn draft saved with message_id=%s",
        generated_content_message_id,
    )

    return {
        "current_agent": "linkedin_writer",
        "topic": topic,
        "target_audience": target_audience,
        "tone": tone,
        "keywords": keywords,
        "objective": objective,
        "linkedin_hook": draft["hook"],
        "linkedin_draft": draft["post_body"],
        "linkedin_hashtags": draft["hashtags"],
        "linkedin_call_to_action": draft["call_to_action"],
        "current_content": full_post,
        "generated_content_message_id": generated_content_message_id,
        "completed_agents": completed_agents,
        "messages": [ AIMessage(content=full_post) ],
    }


def linkedin_writer_test_node(state: ContentState) -> dict:

    topic = state.get("topic", "AI Agents in Software Development")

    # Temporary content for workflow testing
    draft = f"""
    AI agents are transforming software development!

    From automating repetitive tasks to helping developers
    solve complex problems, AI agents are changing how
    we build software.

    What do you think about the future of AI agents?

    #AI #SoftwareDevelopment #AIagents
    """

    return {
        "current_agent": "linkedin_writer",
        "topic": topic,
        "linkedin_draft": draft,
        "current_content": draft,
        "user_id" :"usr_local_001",
        "messages": [
            AIMessage(content=draft)
        ]
    }