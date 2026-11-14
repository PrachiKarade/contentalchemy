
from src.core.logger import setup_logger
from src.core.state import ContentState

logger = setup_logger("multi_agent_orchestrator")


#------------------------------------------------------------
# multi agent orchestrator node
#----------------------------------------------------------------

def multi_agent_orchestrator_node(state: ContentState) -> dict:
    """Select the next requested deliverable in sequence."""

    requested_agents = state.get("requested_agents", [])
    results = dict(state.get("multi_agent_results", {}))

    supported_agents = {
        "research",
        "strategy",
        "blog",
        "linkedin",
        "image",
    }

    for agent in requested_agents:
        if agent not in supported_agents:
            raise ValueError(
                f"Unsupported requested deliverable: {agent}"
            )

    # Record image-generation failure once.
    if (
        state.get("intent") == "multi"
        and state.get("image_status") == "failed"
        and "image" in requested_agents
    ):
        results["image"] = {
            "content": "",
            "content_text": "",
            "message_id": state.get("generated_image_message_id"),
            "status": "failed",
        }

    # Select the next unprocessed deliverable.
    for agent in requested_agents:
        result = results.get(agent, {})

        if result.get("status") in (
            "draft",
            "generated",
            "completed",
            "approved",
            "rejected",
            "failed",
        ):
            continue

        logger.info("Next multi-agent deliverable: %s", agent)

        return {
            "next_agent": agent,
            "multi_agent_results": results,
            "multi_agent_status": "in_progress",
            "current_agent": "multi_agent_orchestrator",
        }

    logger.info("All requested multi-agent deliverables processed.")

    return {
        "next_agent": "",
        "multi_agent_results": results,
        "multi_agent_status": "completed",
        "current_agent": "multi_agent_orchestrator",
    }



#------------------------------------------------------------
# Route multi agent 
#----------------------------------------------------------------
def route_multi_agent(state: ContentState) -> str:
    """Route to the next deliverable or final review."""

    next_agent = state.get("next_agent", "")

    if not next_agent:
        return "complete"

    return next_agent
