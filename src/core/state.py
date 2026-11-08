
from typing import Annotated, Literal
from typing_extensions import TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import Any, add_messages


class ResearchResult(TypedDict, total=False):
    title: str
    url: str
    snippet: str


class HumanInteraction(TypedDict, total=False):
    interaction_type: Literal[ "questionnaire","clarification","content_review","image_review","approval",]                   # used to specify the type of interaction with the human user
    agent: str          # the name of the agent that initiated the interaction
    question: str       # the question or prompt presented to the human user
    options: list[str]  # the possible options or responses provided to the human user
    content: str        # the content related to the interaction
    status: Literal["pending", "completed"] # the status of the interaction
    response: str | dict[str, Any]     # the response provided by the human user
    approved: bool      # whether the interaction has been approved


class ContentState(TypedDict, total=False):
    # Conversation
    messages: Annotated[list[AnyMessage], add_messages] # messages exchanged between the user and the agents, including both user inputs and agent responses

    # Request and routing
    user_request: str   # the original request or prompt provided by the user
    user_id: str             # User ID
    conversation_id: str # conversation id

    # User context
    topic: str          # the topic of the request
    intent: Literal[ "research", "blog", "linkedin", "image", "strategy", "multi"  ]                # the intent or purpose of the request
    
    target_audience: str        # the intended audience for the generated content
    tone: str                   # the desired tone or style of the generated content
    keywords: list[str]         # the keywords or key phrases to be included in the generated content
    objective:str
    #user_profile_markdown: str  # the user's profile information in markdown format

    # Research
    research_results: list[ResearchResult] # the results of the research conducted
    research_summary: str                  # the summary of the research findings
    research_data: dict
    research_report: str    

    # SEO Blog output
    blog_data: dict
    blog_primary_keyword: str
    blog_secondary_keywords: list[str]
    blog_search_intent: str
    blog_outline: list[dict]
    blog_article: str
    blog_call_to_action: str
    
    # LinkedIn structured output
    linkedin_hook: str
    linkedin_draft: str
    linkedin_hashtags: list[str]
    linkedin_call_to_action: str    
    review_action: Literal[ "approve", "edit", "reject"]# Human review decision
    linkedin_edited_draft: str

    
    linkedin_profile_answers: dict[str, list[str]]
    #linkedin_profile_markdown: str

    content_strategy: str   # the strategy for generating the content

      # Image generation
    image_prompt: str
    image_path: str
    image_url: str
    generated_image_message_id: str

    # Image generation preferences
    image_purpose: str
    image_visual_style: str
    image_orientation: Literal["square", "portrait", "landscape"]
    image_quality: Literal["standard", "hd"]
    image_size: Literal["1024x1024", "1024x1792", "1792x1024"]
    image_style: Literal["vivid", "natural"]

    # Image generation tracking
    image_status: Literal[ "pending", "generated",  "approved", "rejected","failed"]
    image_review_action: Literal[  "approve", "edit", "regenerate", "reject"]
    image_error: str
    image_preference_error: str    # why the last preference answer was not accepted
    image_generation_count: int  


    current_content: str    # the currently generated content  
    edited_content : str
    final_content  : str    # the reviewed content: the user's edit, the approved draft, or empty when rejected
    current_agent  : str
    generated_content_message_id: str

    # Shared human interaction
    human_interaction: HumanInteraction | None # the interaction with the human user, including the type of interaction, the agent that initiated it, the question or prompt presented, the options provided, the content related to the interaction, the status of the interaction, the response provided by the human user, feedback about the interaction, and whether it has been approved
    #human_feedback: str                 # feedback provided by the human user regarding the generated content
    
    approval_status: Literal[ "pending", "edited", "approved", "rejected"] # pending review, edited (goes back to review), approved or rejected

    # Workflow tracking
    completed_agents: list[str] # the list of agents that have completed their tasks in the workflow
    errors: list[str] # the list of errors encountered during the workflow execution
