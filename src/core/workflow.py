from langgraph.graph import StateGraph, START, END

from src.core.state import ContentState
from src.core.router import route_by_intent

from src.agents.query_handler import query_handler_node
from src.agents.linkedin_interaction import linkedin_profile_interaction_node
from src.agents.linkedin_writer import linkedin_writer_node
from src.agents.content_writer import content_writer_node
from src.agents.content_review import content_review_node
from src.agents.research_agent import research_agent_node
from src.agents.blog_writer import seo_blog_writer_node
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

    logger.info("Register existing and new nodes")

    # Register nodes
    workflow.add_node("query_handler", query_handler_node)
    workflow.add_node( "linkedin_profile_interaction", linkedin_profile_interaction_node,)
    workflow.add_node("linkedin_writer", linkedin_writer_node)
    workflow.add_node("content_writer", content_writer_node)
    workflow.add_node("image_request_analyzer", image_request_analyzer_node)
    workflow.add_node("image_preference_interaction", image_preference_interaction_node)
    workflow.add_node("image_generator", image_generator_node)
    workflow.add_node("image_review", image_review_node)
    workflow.add_node("content_review", content_review_node)
    workflow.add_node("research_agent", research_agent_node)
    workflow.add_node("seo_blog_writer", seo_blog_writer_node)

    # Entry point
    workflow.add_edge(START, "query_handler")

    # Route based on user intent
    workflow.add_conditional_edges(
        "query_handler",
        route_by_intent,
        {
            "linkedin": "linkedin_profile_interaction",
            "research": "research_agent",
            "blog": "seo_blog_writer",
            "image": "image_request_analyzer",
        },
    )

    # Image preferences: ask for each one missing from the request, one question at a time.
    image_preference_routes = {
        "ask": "image_preference_interaction",
        "generate": "image_generator",
    }
    workflow.add_conditional_edges("image_request_analyzer", route_image_preferences, image_preference_routes)
    workflow.add_conditional_edges("image_preference_interaction", route_image_preferences, image_preference_routes)

    # LinkedIn profile collection → writer
    workflow.add_edge( "linkedin_profile_interaction", "linkedin_writer")

    # LinkedIn writer → shared text review
    workflow.add_edge("linkedin_writer", "content_review")

    # Image generation → image review
    workflow.add_edge("image_generator", "image_review")

    # Other content generators → shared text review
    workflow.add_edge("content_writer", "content_review")
    workflow.add_edge("research_agent", "content_review")
    workflow.add_edge("seo_blog_writer", "content_review")

    # Text review routing
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

    # Image review routing
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

    logger.info("Compile graph with checkpointer")

    return workflow.compile(checkpointer=checkpointer)