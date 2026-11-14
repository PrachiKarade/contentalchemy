from unittest.mock import patch

import pytest
from langgraph.graph import StateGraph, START, END

from src.core.state import ContentState
from src.agents.content_strategist import content_strategist_node


def test_workflow_stops_when_content_strategist_fails():

    executed_nodes = []

    def research_agent(state):
        executed_nodes.append("research_agent")
        return {
            "research_data": {
                "topic": "Agentic AI",
                "research_summary": "Test research summary",
                "findings": [],
                "sources": [],
            }
        }

    def content_generator(state):
        executed_nodes.append("content_generator")
        return {}

    def content_review(state):
        executed_nodes.append("content_review")
        return {}

    graph = StateGraph(ContentState)

    graph.add_node("research_agent", research_agent)
    graph.add_node("content_strategist", content_strategist_node)
    graph.add_node("content_generator", content_generator)
    graph.add_node("content_review", content_review)

    graph.add_edge(START, "research_agent")
    graph.add_edge("research_agent", "content_strategist")
    graph.add_edge("content_strategist", "content_generator")
    graph.add_edge("content_generator", "content_review")
    graph.add_edge("content_review", END)

    app = graph.compile()

    state = {
        "user_id": "test-user",
        "conversation_id": "test-conversation",
        "topic": "Agentic AI",
    }

    with patch(
        "src.agents.content_strategist.get_conversation",
        return_value={
            "target_audience": "Developers",
            "tone": "Professional",
            "objective": "Education",
        },
    ), patch(
        "src.agents.content_strategist.text_provider_manager.generate_text",
        side_effect=RuntimeError("Simulated LLM failure"),
    ):

        with pytest.raises(RuntimeError, match="Simulated LLM failure"):
            app.invoke(state)

    assert executed_nodes == ["research_agent"]