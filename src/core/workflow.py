
from langgraph.graph import StateGraph, START, END

from src.core.state import ContentState
from src.core.router import route_by_intent

from src.agents.query_handler import query_handler_node
from src.agents.linkedin_interaction import linkedin_profile_interaction_node
from src.agents.content_generator import content_generator_node
from src.agents.content_review import content_review_node
from src.agents.research_agent import research_agent_node
from src.agents.content_strategist import content_strategist_node
from src.agents.image_generator import image_generator_node

from src.agents.image_preferences import (
    image_preference_interaction_node,
    image_request_analyzer_node,
    route_image_preferences,
)
from src.agents.image_review import image_review_node

from src.core.logger import setup_logger

logger = setup_logger("AI Content Marketing Assistant Graph")


def build_workflow(checkpointer=None):

    workflow = StateGraph(ContentState)

    logger.info("Registering workflow nodes")

    # ------------------------------------------------
    # 1. Register nodes
    # ------------------------------------------------

    workflow.add_node("query_handler", query_handler_node)

    workflow.add_node(
        "linkedin_profile_interaction",
        linkedin_profile_interaction_node,
    )

    workflow.add_node("research_agent", research_agent_node)
    workflow.add_node("content_strategist", content_strategist_node)
    workflow.add_node("content_generator", content_generator_node)
    workflow.add_node("content_review", content_review_node)

    # Image workflow
    workflow.add_node("image_request_analyzer", image_request_analyzer_node)
    workflow.add_node( "image_preference_interaction", image_preference_interaction_node)
    workflow.add_node("image_generator", image_generator_node)
    workflow.add_node("image_review", image_review_node)

    # ------------------------------------------------
    # 2. Entry point
    # ------------------------------------------------

    workflow.add_edge(START, "query_handler")

    # ------------------------------------------------
    # 3. Route based on user intent
    # ------------------------------------------------

    workflow.add_conditional_edges(
        "query_handler",
        route_by_intent,
        {
            "linkedin": "linkedin_profile_interaction",
            "research": "research_agent",
            "blog": "research_agent",
            "image": "image_request_analyzer",
        },
    )

    # ------------------------------------------------
    # 4. LinkedIn workflow
    # ------------------------------------------------

    # Collect LinkedIn profile before generating content.
    workflow.add_edge(  "linkedin_profile_interaction", "research_agent")

    # ------------------------------------------------
    # 5. Research and content strategy workflow
    # ------------------------------------------------

    workflow.add_edge("research_agent", "content_strategist")

    # Research-only requests go to review.
    # Blog requests continue to content generation.
    def route_after_strategy(state: ContentState):
        intent = state.get("intent", "").strip().lower()

        if intent == "research":
            return "content_review"

        if intent in ("linkedin", "blog", "seo_blog"):
            return "content_generator"
        
        logger.warning(  "Unsupported intent after content strategy: %s",  intent)
        return "end"

    workflow.add_conditional_edges(
        "content_strategist",
        route_after_strategy,
        {
            "content_review": "content_review",
            "content_generator": "content_generator",
            "end": END,
        },
    )

    # ------------------------------------------------
    # 6. Content generation and review
    # ------------------------------------------------

    workflow.add_edge("content_generator", "content_review")

    # Edited content returns to review.
    # Approved or rejected content ends the workflow.
    def route_after_review(state: ContentState):
        if state.get("approval_status") == "edited":
            return "content_review"

        return END

    workflow.add_conditional_edges(
        "content_review",
        route_after_review,
        {
            "content_review": "content_review",
            END: END,
        },
    )

    # ------------------------------------------------
    # 7. Image preferences workflow
    # ------------------------------------------------

    image_preference_routes = {
        "ask": "image_preference_interaction",
        "generate": "image_generator",
    }

    workflow.add_conditional_edges(
        "image_request_analyzer",
        route_image_preferences,
        image_preference_routes,
    )

    workflow.add_conditional_edges(
        "image_preference_interaction",
        route_image_preferences,
        image_preference_routes,
    )

    # ------------------------------------------------
    # 8. Image generation and review
    # ------------------------------------------------

    def route_after_image_generation(state: ContentState):
        if state.get("image_status") == "failed":
            logger.warning("Image generation failed. Ending workflow.")
            return "end"

        return "review"

    workflow.add_conditional_edges(
        "image_generator",
        route_after_image_generation,
        {
            "review": "image_review",
            "end": END,
        },
    )

    # Handle image review decisions.
    def route_after_image_review(state: ContentState):
        return state.get("image_review_action")

    workflow.add_conditional_edges(
        "image_review",
        route_after_image_review,
        {
            "approve": END,
            "edit": "image_generator",
            "regenerate": "image_generator",
            "reject": END,
        },
    )

    # ------------------------------------------------
    # 9. Compile workflow
    # ------------------------------------------------

    logger.info("Compiling graph with checkpointer")

    return workflow.compile(checkpointer=checkpointer)
