import time
from functools import wraps
from langgraph.graph import StateGraph, START, END

from src.core.state import ContentState
from src.core.router import route_by_intent

from src.agents.query_handler import query_handler_node
from src.agents.linkedin_interaction import linkedin_profile_interaction_node
from src.agents.content_generator import (content_generator_node,multi_content_generator_node)
from src.agents.content_review import (content_review_node,multi_content_review_node)
from src.agents.research_agent import research_agent_node
from src.agents.content_strategist import content_strategist_node
from src.agents.image_generator import image_generator_node
from src.agents.multi_agent_orchestrator import (
    multi_agent_orchestrator_node,
    route_multi_agent,
)
from langgraph.errors import GraphInterrupt

from src.agents.image_preferences import (
    image_preference_interaction_node,
    image_request_analyzer_node,
    route_image_preferences,
)
from src.agents.image_review import image_review_node

from src.core.logger import setup_logger

logger = setup_logger("AI Content Marketing Assistant Graph")


def track_node_execution(node_name: str, node_function):
    """Measure execution time for each LangGraph node."""

    @wraps(node_function)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        status = "incomplete"

        logger.info("Node started: %s", node_name)

        try:
            result = node_function(*args, **kwargs)
            status = "completed"
            return result
        
        except GraphInterrupt:
            status = "interrupted"
            raise

        except Exception:
            status = "failed"
            logger.exception("Node failed: %s", node_name)
            raise

        finally:
            elapsed = time.perf_counter() - start_time

            logger.info(
                "Node finished | Node: %s | Status: %s | "
                "Execution time: %.2f seconds",
                node_name,
                status,
                elapsed,
            )

    return wrapper


# Multi deliverables that need the research agent and content strategist first.
RESEARCH_BASED_DELIVERABLES = {"research", "strategy", "blog", "linkedin"}


def route_after_query_handler(state: ContentState) -> str:
    """Route by intent. Multi requests start with the first step their deliverables need."""

    intent = route_by_intent(state)

    if intent == "multi":
        requested_agents = state.get("requested_agents", [])

        # LinkedIn asks its profile questions before research.
        if "linkedin" in requested_agents:
            return "linkedin"

        if RESEARCH_BASED_DELIVERABLES.intersection(requested_agents):
            return "research"

        # Image-only: no research needed.
        return "multi"

    return intent


# ---------------------------------------------------------------
# Build graph  
# ------------------------------------------------------------------------

def build_workflow(checkpointer=None):

    workflow = StateGraph(ContentState)

    logger.info("Registering workflow nodes")

    # ------------------------------------------------
    # 1. Register nodes
    # ------------------------------------------------

    workflow.add_node("query_handler",  track_node_execution("query_handler", query_handler_node),)

    workflow.add_node(
    "linkedin_profile_interaction",
    track_node_execution(
        "linkedin_profile_interaction",
        linkedin_profile_interaction_node,
    ),
    )

    workflow.add_node(
        "research_agent",
        track_node_execution("research_agent", research_agent_node),
    )

    workflow.add_node(
        "content_strategist",
        track_node_execution("content_strategist", content_strategist_node),
    )

    workflow.add_node(
        "content_generator",
        track_node_execution("content_generator", content_generator_node),
    )

    workflow.add_node(
        "content_review",
        track_node_execution("content_review", content_review_node),
    )

    # Image workflow
    workflow.add_node(
        "image_request_analyzer",
        track_node_execution(
            "image_request_analyzer",
            image_request_analyzer_node,
        ),
    )

    workflow.add_node(
        "image_preference_interaction",
        track_node_execution(
            "image_preference_interaction",
            image_preference_interaction_node,
        ),
    )

    workflow.add_node(
        "image_generator",
        track_node_execution("image_generator", image_generator_node),
    )

    workflow.add_node(
        "image_review",
        track_node_execution("image_review", image_review_node),
    )

    workflow.add_node(
    "multi_agent_orchestrator",
    track_node_execution(
        "multi_agent_orchestrator",
        multi_agent_orchestrator_node,
    ),
    )

    workflow.add_node(
        "multi_content_generator",
        track_node_execution(
            "multi_content_generator",
            multi_content_generator_node,
        ),
    )

    workflow.add_node(
        "multi_content_review",
        track_node_execution(
            "multi_content_review",
            multi_content_review_node,
        ),
    )

    # ------------------------------------------------
    # 2. Entry point
    # ------------------------------------------------

    workflow.add_edge(START, "query_handler")

    # ------------------------------------------------
    # 3. Route based on user intent
    # ------------------------------------------------
    workflow.add_conditional_edges(
        "query_handler",
        route_after_query_handler,
        {
            "linkedin": "linkedin_profile_interaction",
            "research": "research_agent",
            "blog": "research_agent",
            "image": "image_request_analyzer",
            "multi": "multi_agent_orchestrator",
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

    def route_after_research(state: ContentState):
        intent = state.get("intent", "").strip().lower()
        requested_agents = state.get("requested_agents", [])

        # Research-only requests should skip content strategy.
        if intent == "research" and "strategy" not in requested_agents:
            return "review"

        return "strategy"


    workflow.add_conditional_edges(
        "research_agent",
        route_after_research,
        {
            "review": "content_review",
            "strategy": "content_strategist",
        },
    )

    # Research-only requests go to review.
    # Blog requests continue to content generation.
    def route_after_strategy(state: ContentState):
        intent = state.get("intent", "").strip().lower()

        if intent == "research":
            return "content_review"

        if intent in ("linkedin", "blog", "seo_blog"):
            return "content_generator"

        if intent == "multi":
            return "multi_agent_orchestrator"

        
        logger.warning(  "Unsupported intent after content strategy: %s",  intent)
        return "end"

    workflow.add_conditional_edges(
        "content_strategist",
        route_after_strategy,
        {
            "content_review": "content_review",
            "content_generator": "content_generator",
            "multi_agent_orchestrator": "multi_agent_orchestrator",
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
    # Multi-agent workflow
    # ------------------------------------------------

    workflow.add_conditional_edges(
        "multi_agent_orchestrator",
        route_multi_agent,
        {
            "blog": "multi_content_generator",
            "linkedin": "multi_content_generator",
            "image": "image_request_analyzer",
            "complete": "multi_content_review",
        },
    )

    # After generating blog or LinkedIn content,
    # return to the orchestrator for the next deliverable.
    workflow.add_edge( "multi_content_generator", "multi_agent_orchestrator", )

    # After reviewing all requested text deliverables,
    # finish the multi-agent workflow.
    workflow.add_edge("multi_content_review", END)

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
            logger.warning("Image generation failed.")

            if state.get("intent") == "multi":
                return "multi"

            return "end"

        return "review"

    workflow.add_conditional_edges(
        "image_generator",
        route_after_image_generation,
        {
            "review": "image_review",
            "multi": "multi_agent_orchestrator",
            "end": END,
        },
    )

    # Handle image review decisions.

    def route_after_image_review(state: ContentState):
        action = state.get("image_review_action")

        if state.get("intent") == "multi":
            if action in ("approve", "reject"):
                return "multi"

        return action

    # ------------- image review conditional edge ------------------------------------

    workflow.add_conditional_edges(
        "image_review",
        route_after_image_review,
        {
            "approve": END,
            "edit": "image_generator",
            "regenerate": "image_generator",
            "reject": END,
            "multi": "multi_agent_orchestrator",
        },
    )

    # ------------------------------------------------
    # 9. Compile workflow
    # ------------------------------------------------

    logger.info("Compiling graph with checkpointer")

    return workflow.compile(checkpointer=checkpointer)
