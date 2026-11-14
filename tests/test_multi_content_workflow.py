"""Multi-content workflow: routing, review payloads, and a full run with stubbed agents."""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt

import src.agents.content_review as content_review
import src.agents.image_review as image_review
import src.core.workflow as workflow
from src.agents.image_generator import multi_image_request
from src.agents.multi_agent_orchestrator import multi_agent_orchestrator_node, route_multi_agent
from src.core.workflow import route_after_query_handler
from src.web_app.components.multi_view import workflow_steps


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (["linkedin", "blog", "image"], "linkedin"),
        (["blog", "image"], "research"),
        (["research", "strategy"], "research"),
        (["image"], "multi"),
    ],
)
def test_multi_routes_to_first_needed_step(requested, expected):
    assert route_after_query_handler({"intent": "multi", "requested_agents": requested}) == expected


@pytest.mark.parametrize("intent", ["research", "blog", "linkedin", "image"])
def test_single_intents_route_unchanged(intent):
    assert route_after_query_handler({"intent": intent, "requested_agents": ["image"]}) == intent


def test_orchestrator_walks_requested_in_order():
    state = {
        "intent": "multi",
        "requested_agents": ["linkedin", "blog", "image"],
        "multi_agent_results": {"linkedin": {"status": "draft"}},
    }

    update = multi_agent_orchestrator_node(state)

    assert update["next_agent"] == "blog"
    assert route_multi_agent({**state, **update}) == "blog"


def test_orchestrator_records_failed_image_and_completes():
    state = {
        "intent": "multi",
        "requested_agents": ["blog", "image"],
        "image_status": "failed",
        "multi_agent_results": {"blog": {"status": "draft"}},
    }

    update = multi_agent_orchestrator_node(state)

    assert update["multi_agent_results"]["image"]["status"] == "failed"
    assert route_multi_agent({**state, **update}) == "complete"


def test_multi_image_request_focuses_on_topic():
    request = multi_image_request(
        {"topic": "AI in marketing", "user_request": "Write a blog and a LinkedIn post about AI in marketing with an image"}
    )

    assert request.startswith("An image about: AI in marketing")
    assert "create only the image" in request


# ---------------------------------------------------------------------------
# Multi review payload
# ---------------------------------------------------------------------------


def test_multi_review_payload_has_deliverable_and_quality(monkeypatch):
    payloads = []

    def fake_interrupt(payload):
        payloads.append(payload)
        return {"action": "approve"}

    monkeypatch.setattr(content_review, "interrupt", fake_interrupt)
    monkeypatch.setattr(content_review, "update_message", lambda **kwargs: True)

    state = {
        "user_id": "usr_1",
        "conversation_id": "conv_1",
        "requested_agents": ["blog"],
        "multi_agent_results": {
            "blog": {
                "content_text": "## Blog",
                "content_type": "seo_blog",
                "message_id": "msg_1",
                "status": "draft",
                "quality_score": 82,
                "quality_grade": "Good",
                "quality_details": {"title": 15},
                "quality_suggestions": [],
            }
        },
    }

    update = content_review.multi_content_review_node(state)

    assert payloads[0]["deliverable"] == "blog"
    assert payloads[0]["multi"] is True
    assert payloads[0]["quality"]["score"] == 82
    assert update["multi_agent_results"]["blog"]["status"] == "approved"


def test_multi_review_edit_survives_failed_rescore(monkeypatch):
    monkeypatch.setattr(content_review, "interrupt", lambda payload: {"action": "edit", "edited_content": "Edited post"})
    monkeypatch.setattr(content_review, "update_message", lambda **kwargs: True)
    monkeypatch.setattr(content_review, "rescore", lambda *args: None)

    state = {
        "user_id": "usr_1",
        "conversation_id": "conv_1",
        "requested_agents": ["linkedin"],
        "multi_agent_results": {
            "linkedin": {"content_text": "Post", "content_type": "linkedin", "message_id": "msg_1", "status": "draft"}
        },
    }

    update = content_review.multi_content_review_node(state)

    result = update["multi_agent_results"]["linkedin"]
    assert result["status"] == "approved"
    assert result["content_text"] == "Edited post"


# ---------------------------------------------------------------------------
# Full graph run with stubbed agents
# ---------------------------------------------------------------------------


def stub_agents(monkeypatch):
    """Replace the LLM / database agents; keep routing, orchestrator, reviews and interrupts real."""

    def query_handler(state):
        return {"intent": "multi", "topic": "AI in marketing", "requested_agents": ["linkedin", "blog", "image"]}

    def profile(state):
        answer = interrupt({"interaction_type": "linkedin_profile_question", "question": "Role?", "options": []})
        return {"linkedin_profile_answers": {"current_role": answer["selected_options"]}}

    def research(state):
        return {"research_data": {"topic": "AI"}, "completed_agents": ["research_agent"]}

    def strategist(state):
        completed = state.get("completed_agents", []) + ["content_strategist"]
        return {"research_report": "Report", "content_strategy": "Strategy", "completed_agents": completed}

    def writer(state):
        results = dict(state.get("multi_agent_results", {}))
        agent = state["next_agent"]
        results[agent] = {
            "content_text": f"{agent} draft",
            "content_type": "seo_blog" if agent == "blog" else agent,
            "message_id": f"msg_{agent}",
            "status": "draft",
        }
        return {"multi_agent_results": results, "current_agent": f"{agent}_writer"}

    def analyzer(state):
        return {"image_purpose": "Blog", "image_visual_style": "Minimalist", "image_orientation": "landscape"}

    def image_generator(state):
        return {"image_path": "generated/image.png", "image_prompt": "Prompt", "image_status": "generated",
                "generated_image_message_id": "msg_image"}

    monkeypatch.setattr(workflow, "query_handler_node", query_handler)
    monkeypatch.setattr(workflow, "linkedin_profile_interaction_node", profile)
    monkeypatch.setattr(workflow, "research_agent_node", research)
    monkeypatch.setattr(workflow, "content_strategist_node", strategist)
    monkeypatch.setattr(workflow, "multi_content_generator_node", writer)
    monkeypatch.setattr(workflow, "image_request_analyzer_node", analyzer)
    monkeypatch.setattr(workflow, "image_generator_node", image_generator)
    monkeypatch.setattr(image_review, "update_message", lambda **kwargs: True)
    monkeypatch.setattr(content_review, "update_message", lambda **kwargs: True)


def run(graph, config, value):
    graph.invoke(value, config)
    snapshot = graph.get_state(config)
    return (snapshot.interrupts[0].value if snapshot.interrupts else None), snapshot.values


def test_full_multi_run_interrupts_in_agent_order(monkeypatch):
    stub_agents(monkeypatch)
    graph = workflow.build_workflow(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "multi-test"}}

    # 1. LinkedIn profile question.
    payload, _ = run(graph, config, {"intent": "multi", "user_id": "usr_1", "conversation_id": "conv_1", "user_request": "LinkedIn post, SEO blog and image on AI"})
    assert payload["interaction_type"] == "linkedin_profile_question"

    # 2. Research, strategy, both writers, then the one missing image preference.
    payload, state = run(graph, config, Command(resume={"selected_options": ["AI Engineer"], "other_text": ""}))
    assert payload["interaction_type"] == "image_preference_question"
    assert payload["lookup_key"] == "image_quality"
    assert {"linkedin", "blog"} <= set(state["multi_agent_results"])
    assert workflow_steps(
        {"requested": ["linkedin", "blog", "image"], "items": {}, "progress": {"profile": True}}
    )[0] == {"label": "Profile questions", "done": True, "interrupt": True}

    # 3. Image review.
    payload, _ = run(graph, config, Command(resume={"selected_options": ["HD"], "other_text": ""}))
    assert payload["interaction_type"] == "image_review"

    # 4. Approve the image: the text deliverables come up for review one by one.
    payload, _ = run(graph, config, Command(resume={"action": "approve"}))
    assert payload["interaction_type"] == "content_review"
    assert payload["deliverable"] == "linkedin"

    payload, _ = run(graph, config, Command(resume={"action": "reject"}))
    assert payload["deliverable"] == "blog"

    payload, state = run(graph, config, Command(resume={"action": "edit", "edited_content": "Edited blog"}))
    assert payload is None

    results = state["multi_agent_results"]
    assert results["image"]["status"] == "approved"
    assert results["linkedin"]["status"] == "rejected"
    assert results["blog"]["status"] == "approved"
    assert results["blog"]["content_text"] == "Edited blog"


def test_image_only_multi_skips_research(monkeypatch):
    stub_agents(monkeypatch)
    monkeypatch.setattr(
        workflow,
        "query_handler_node",
        lambda state: {"intent": "multi", "topic": "AI", "requested_agents": ["image"]},
    )
    monkeypatch.setattr(
        workflow,
        "research_agent_node",
        lambda state: pytest.fail("Image-only multi requests must not run research."),
    )
    graph = workflow.build_workflow(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "multi-image-only"}}

    payload, _ = run(graph, config, {"intent": "multi", "user_request": "Just an image about AI"})

    assert payload["interaction_type"] == "image_preference_question"


# ---------------------------------------------------------------------------
# Step-by-step run: one agent step per call, each shown in its content type's tab
# ---------------------------------------------------------------------------


def test_step_by_step_run_hands_off_between_content_type_tabs(monkeypatch):
    from src.web_app.assistant import MULTI_STEP_NODES
    from src.web_app.components.state import step_owner

    stub_agents(monkeypatch)
    graph = workflow.build_workflow(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "multi-steps"}}
    multi = {"requested": []}

    def step(value):
        """Like assistant.advance_multi: run until the next pause; return (payload, state, next nodes)."""

        for _mode, update in graph.stream(value, config, stream_mode=["updates"], interrupt_after=MULTI_STEP_NODES):
            # A pause from interrupt_after comes through with no payload.
            assert "__interrupt__" not in update or isinstance(update["__interrupt__"], tuple)
        snapshot = graph.get_state(config)
        payload = snapshot.interrupts[0].value if snapshot.interrupts else None
        return payload, snapshot.values, tuple(snapshot.next)

    def run_owners(value):
        """Step until an agent needs the user; return the tab that showed each step."""

        owners = []
        owner = None
        while True:
            payload, state, next_nodes = step(value)
            value = None
            multi["requested"] = state.get("requested_agents", [])
            if payload is not None or not next_nodes:
                return owners, payload
            owner = step_owner(next_nodes[0], state, multi, owner)
            if not owners or owners[-1] != owner:
                owners.append(owner)

    initial = {"intent": "multi", "user_id": "usr_1", "conversation_id": "conv_1", "user_request": "Post, blog and image"}

    # Request analysis, then the LinkedIn tab asks its profile question.
    owners, payload = run_owners(initial)
    assert owners == ["linkedin"]
    assert payload["interaction_type"] == "linkedin_profile_question"

    # Research and strategy show in the LinkedIn tab (the first text type), then each writer
    # in its own tab, then the image tab asks for the missing preference.
    owners, payload = run_owners(Command(resume={"selected_options": ["AI Engineer"], "other_text": ""}))
    assert owners == ["linkedin", "blog", "image"]
    assert payload["interaction_type"] == "image_preference_question"


def test_step_owner_maps_agents_to_content_type_tabs():
    from src.web_app.components.state import step_owner

    multi = {"requested": ["blog", "research", "image"]}

    assert step_owner("query_handler", {}, multi, None) is None
    assert step_owner("research_agent", {}, multi, "blog") == "research"
    assert step_owner("multi_content_generator", {"next_agent": "blog"}, multi, "research") == "blog"
    assert step_owner("image_generator", {}, multi, "blog") == "image"
    assert step_owner("multi_agent_orchestrator", {}, multi, "blog") == "blog"
