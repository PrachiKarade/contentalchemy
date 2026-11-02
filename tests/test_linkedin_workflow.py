"""LinkedIn workflow with human-in-the-loop interrupts.

The workflow pauses twice:
1. linkedin_profile_interaction asks five profile questions (one interrupt each).
2. content_review asks the user to approve, edit or reject the draft.
   An edited draft comes back for review so the user can approve it.

Run interactively (answer the questions and review the draft yourself):
    python -m tests.test_linkedin_workflow

Run with scripted answers for approve, edit and reject:
    python -m tests.test_linkedin_workflow --auto
"""

import logging
import sys
import os
from dotenv import load_dotenv

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.core.workflow import build_workflow
from src.repositories.conversation_repository import create_conversation, delete_conversation
from src.repositories.message_repository import get_messages_collection


load_dotenv()

os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")

# Use a valid user ID from your application's user collection.
USER_ID = "usr_local_001"

TOPIC = "How MCP helps AI agents connect with external tools"

REVIEW_ACTIONS = {"a": "approve", "e": "edit", "r": "reject"}


# --------------------------------------------------
# Workflow runner
# --------------------------------------------------


def get_interrupt_payload(result: dict) -> dict | None:
    """Extract the payload passed to interrupt(), if the workflow paused."""

    interrupts = result.get("__interrupt__", [])
    return interrupts[0].value if interrupts else None


def run_linkedin_workflow(answer_question, review_content) -> dict:
    """Run the workflow, resuming each interrupt with the user's response.

    answer_question(payload) -> {"selected_options": [...], "other_text": "..."}
    review_content(payload)  -> {"action": "approve" | "edit" | "reject", "edited_content": "..."}

    Returns the final workflow state.
    """

    workflow = build_workflow(checkpointer=MemorySaver())

    # linkedin_writer_node loads the conversation, so create a real one.
    conversation = create_conversation(
        user_id=USER_ID,
        content_type="linkedin",
        title=TOPIC,
        topic=TOPIC,
        target_audience="AI developers",
    )
    conversation_id = conversation["conversation_id"]

    # The same thread_id must be used for every resume.
    config = {"configurable": {"thread_id": conversation_id}}

    initial_state = {
        "user_id": USER_ID,
        "conversation_id": conversation_id,
        "user_request": f"Create a LinkedIn post about {TOPIC.lower()}.",
        "topic": TOPIC,
        "intent": "linkedin",
        "target_audience": "AI developers",
        "keywords": ["MCP", "AI Agents", "Tool Integration"],
        "completed_agents": [],
        "errors": [],
    }

    try:
        result = workflow.invoke(initial_state, config=config)

        # Keep resuming until the workflow stops asking for input.
        while (payload := get_interrupt_payload(result)) is not None:
            interaction_type = payload.get("interaction_type")

            if interaction_type == "linkedin_profile_question":
                response = answer_question(payload)
            elif interaction_type == "content_review":
                response = review_content(payload)
            else:
                raise ValueError(f"Unexpected interrupt: {interaction_type!r}")

            result = workflow.invoke(Command(resume=response), config=config)

        return workflow.get_state(config).values
    finally:
        get_messages_collection().delete_many({"conversation_id": conversation_id})
        delete_conversation(conversation_id, USER_ID)


def print_result(state: dict) -> None:
    print("\n" + "=" * 70)
    print("Approval status:", state.get("approval_status"))
    print("Review action:  ", state.get("review_action"))
    print("\nFinal content:\n")
    print(state.get("final_content") or "(none - the draft was rejected)")
    print("=" * 70)


# --------------------------------------------------
# Interactive responses (console input)
# --------------------------------------------------


def read_input(prompt: str) -> str:
    """input() with a clear message when no keyboard input is available."""

    try:
        return input(prompt)
    except EOFError:
        raise SystemExit(
            "\nNo keyboard input available. Run this in a terminal:\n"
            "    python -m tests.test_linkedin_workflow\n"
            "or use scripted answers:\n"
            "    python -m tests.test_linkedin_workflow --auto"
        ) from None


def ask_question(payload: dict) -> dict:
    """Show a profile question and read the user's choices."""

    options = payload["options"]

    print("\n" + payload["question"])
    for number, option in enumerate(options, start=1):
        print(f"  {number}. {option}")

    while True:
        raw = read_input("Choose one or more numbers, separated by commas: ")
        try:
            numbers = [int(part) for part in raw.split(",") if part.strip()]
        except ValueError:
            numbers = []

        if numbers and all(1 <= number <= len(options) for number in numbers):
            break
        print(f"Please enter numbers between 1 and {len(options)}.")

    selected = [options[number - 1] for number in numbers]

    other_text = ""
    if "Other" in selected:
        while not other_text:
            other_text = read_input("Type your own answer: ").strip()

    return {"selected_options": selected, "other_text": other_text}


def read_multiline(prompt: str) -> str:
    print(prompt)
    lines = []
    while (line := read_input("")) != "END":
        lines.append(line)
    return "\n".join(lines).strip()


def ask_review(payload: dict) -> dict:
    """Show the generated draft and read the approve / edit / reject decision."""

    print("\n" + "-" * 70)
    print(payload["question"])
    print("-" * 70)
    print(payload["content"])
    print("-" * 70)

    while True:
        choice = read_input("Approve, edit or reject? [a/e/r]: ").strip().lower()
        action = REVIEW_ACTIONS.get(choice[:1])
        if action:
            break
        print("Please type a, e or r.")

    if action != "edit":
        return {"action": action, "edited_content": ""}

    edited_content = ""
    while not edited_content:
        edited_content = read_multiline("Paste your edited post. Type END on its own line to finish:")

    return {"action": "edit", "edited_content": edited_content}


# --------------------------------------------------
# Scripted responses (automated run)
# --------------------------------------------------

PROFILE_RESPONSES = {
    "professional_identity": {"selected_options": ["Backend Developer", "AI/ML Enthusiast"], "other_text": ""},
    "current_role": {"selected_options": ["Senior Software Engineer"], "other_text": ""},
    "linkedin_objective": {"selected_options": ["Build a professional brand", "Share AI/ML learning"], "other_text": ""},
    "experience_level": {"selected_options": ["12+ years of IT experience"], "other_text": ""},
    "preferred_tone": {"selected_options": ["Other"], "other_text": "Educational but friendly"},
}

EDITED_POST = "MCP gives AI agents one standard way to reach tools.\n\n#MCP #AIAgents"


def test_linkedin_workflow(action: str = "approve") -> None:
    asked = []

    def scripted_answer(payload: dict) -> dict:
        asked.append(payload["lookup_key"])
        print("Question:", payload["question"])
        return PROFILE_RESPONSES[payload["lookup_key"]]

    reviews = []

    def scripted_review(payload: dict) -> dict:
        assert payload["content"].strip(), "The review interrupt has no draft."
        reviews.append(payload["content"])

        # An edited draft comes back for review; approve it the second time.
        if action == "edit" and len(reviews) == 1:
            return {"action": "edit", "edited_content": EDITED_POST}
        if action == "edit":
            assert payload["content"] == EDITED_POST, "The edited draft was not sent back for review."
            return {"action": "approve", "edited_content": ""}
        return {"action": action, "edited_content": ""}

    state = run_linkedin_workflow(scripted_answer, scripted_review)
    print_result(state)

    assert asked == list(PROFILE_RESPONSES), f"Unexpected questions: {asked}"
    assert state["linkedin_profile_answers"]["preferred_tone"] == ["Educational but friendly"]
    assert state["review_action"] == ("approve" if action == "edit" else action)

    if action == "approve":
        assert state["approval_status"] == "approved"
        assert state["final_content"] == state["current_content"]
    elif action == "edit":
        assert len(reviews) == 2
        assert state["approval_status"] == "approved"
        assert state["final_content"] == EDITED_POST
    else:
        assert state["approval_status"] == "rejected"
        assert state["final_content"] == ""

    print(f"\n{action}: test passed.")


if __name__ == "__main__":
    if "--auto" in sys.argv:
        for review_action in ["approve", "edit", "reject"]:
            test_linkedin_workflow(review_action)
    else:
        # Hide INFO logs so the questions and prompts are easy to see.
        logging.disable(logging.INFO)
        try:
            print_result(run_linkedin_workflow(ask_question, ask_review))
        except KeyboardInterrupt:
            print("\nStopped.")
