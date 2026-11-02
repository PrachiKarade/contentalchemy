from pathlib import Path
from langgraph.types import interrupt
from src.core.logger import setup_logger


# Keep the existing Input directory to avoid changing your project structure.
PROFILE_FILE = Path("inputs/user_profile.md")


LINKEDIN_PROFILE_QUESTIONS = [
    {
        "key": "professional_identity",
        "question": "How would you describe yourself professionally?",
        "options": [
            "Software Developer",
            "Backend Developer",
            "Full Stack Developer",
            "AI/ML Enthusiast",
            "AI Engineer",
            "Technology Professional",
            "Other",
        ],
    },
    {
        "key": "current_role",
        "question": "What is your current title or role?",
        "options": [
            "Software Engineer",
            "Senior Software Engineer",
            "Technical Lead",
            "AI Engineer",
            "ML Engineer",
            "Independent Learner",
            "Other",
        ],
    },
    {
        "key": "linkedin_objective",
        "question": "What is your main objective on LinkedIn?",
        "options": [
            "Share technical knowledge",
            "Build a professional brand",
            "Share AI/ML learning",
            "Connect with professionals",
            "Explore career opportunities",
            "Share projects and experiences",
            "Other",
        ],
    },
    {
        "key": "experience_level",
        "question": "What best describes your experience level?",
        "options": [
            "Entry level",
            "Mid level",
            "Senior level",
            "Lead / Architect",
            "12+ years of IT experience",
            "Other",
        ],
    },
    {
        "key": "preferred_tone",
        "question": "What tone do you prefer for your LinkedIn posts?",
        "options": [
            "Professional",
            "Conversational",
            "Educational",
            "Thought leadership",
            "Friendly and approachable",
            "Storytelling",
            "Other",
        ],
    },
]


def _format_answer(selected_options, other_text):
    """Convert the user's selected options and Other text into readable text."""
    selected_options = selected_options or []

    if isinstance(selected_options, str):
        selected_options = [selected_options]

    answers = [
        option for option in selected_options
        if option != "Other"
    ]

    if other_text and other_text.strip():
        answers.append(other_text.strip())

    return answers


def linkedin_profile_interaction_node(state: dict) -> dict:

    logger = setup_logger("linkedin_profile_interaction")

    answers = {}

    for question in LINKEDIN_PROFILE_QUESTIONS:

        lookup_key = question["key"]

        logger.info("Collecting LinkedIn input: %s", lookup_key)

        if lookup_key:
            logger.info("Found identifier: %s", lookup_key)
        else:
            logger.info("No identifier found — interrupting for user input")

        logger.info("Entering LinkedIn profile interaction node")
        response = interrupt({
            "interaction_type": "linkedin_profile_question",
            "lookup_key": lookup_key,
            "question": question["question"],
            "options": question["options"],
            "selection_type": "multiple",
            "allow_other": True,
        })
        
        logger.info("Resumed profile question: %s", question["key"])

        selected_options = response.get("selected_options", [])
        other_text = response.get("other_text", "")

        if isinstance(selected_options, str):
            selected_options = [selected_options]

        answer = [
            option for option in selected_options
            if option != "Other"
        ]

        if other_text and other_text.strip():
            answer.append(other_text.strip())

        if not answer:
            raise ValueError(f"Answer required for {lookup_key}")

        logger.info("User provided: %s", lookup_key)

        answers[lookup_key] = answer

    return {
        "linkedin_profile_answers": answers,
        "current_agent": "linkedin_profile_interaction",
    }