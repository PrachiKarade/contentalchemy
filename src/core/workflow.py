from langgraph.graph import StateGraph, START, END
from src.core.state import ContentState
from src.core.router import route_by_intent
from src.agents.query_handler import query_handler_node
from src.agents.linkedin_interaction import ( linkedin_profile_interaction_node,)
from src.agents.linkedin_writer import linkedin_writer_node
from src.agents.content_writer import content_writer_node
from src.agents.content_review import content_review_node
from src.agents.research_agent import research_agent_node
from src.agents.blog_writer import seo_blog_writer_node
from src.core.logger import setup_logger
from langgraph.checkpoint.memory import MemorySaver

# Reuse your existing image generator
from src.agents.image_generator import image_generator_node

logger = setup_logger(" AI Content Marketing Assistant Graph. ")

def build_workflow( checkpointer = None):

    workflow = StateGraph(ContentState)

    logger.info("Register existing and new nodes")
    
    workflow.add_node("query_handler", query_handler_node)

    workflow.add_node( "linkedin_profile_interaction",  linkedin_profile_interaction_node,  )

    workflow.add_node("linkedin_writer", linkedin_writer_node) # linkedin_writer_node

    workflow.add_node("content_writer", content_writer_node)

    workflow.add_node("image_generator", image_generator_node)

    workflow.add_node("content_review", content_review_node)

    workflow.add_node("research_agent", research_agent_node)
    workflow.add_node("seo_blog_writer", seo_blog_writer_node)

    logger.info("Entry point of graph : query_handler")
   
    workflow.add_edge(START, "query_handler")

    # ------------------------------------------------
    # 3. Route based on user intent
 
    workflow.add_conditional_edges( "query_handler",
        route_by_intent,
        {
            "linkedin": "linkedin_profile_interaction",
            "research": "research_agent",
            "blog"    : "seo_blog_writer",
            # Placeholder writer until the dedicated agents exist.          
            "image": "content_writer",
      
        },
    )

    # ------------------------------------------------
    # 4. LinkedIn profile collection → writer
    # ------------------------------------------------
    workflow.add_edge( "linkedin_profile_interaction",  "linkedin_writer", )
    # ------------------------------------------------
    # 5. LinkedIn writer → optional image generation
    # ------------------------------------------------
    # The writer should set generate_image=True when an
    # image is requested. Otherwise, skip image generation.
    def route_after_linkedin_writer(state: ContentState):
        if state.get("generate_image", False):
            return "image_generator"

        return "content_review"

    workflow.add_conditional_edges( "linkedin_writer",
        route_after_linkedin_writer,
        {
            "image_generator": "image_generator",
            "content_review": "content_review",
        },
    )
    # ------------------------------------------------
    # 6. Research report → shared review (approve / edit / reject), like every other draft.
    # ------------------------------------------------
    workflow.add_edge("image_generator", "content_review")
    workflow.add_edge("content_writer", "content_review")    
    workflow.add_edge("research_agent", "content_review")
    workflow.add_edge("seo_blog_writer", "content_review")
    # ------------------------------------------------
    # 7. Shared review → END, or back to review after an edit
    # ------------------------------------------------
    # An edited draft goes back to review so the user can approve it.
    def route_after_review(state: ContentState):
        if state.get("approval_status") == "edited":
            return "content_review"

        return END

    workflow.add_conditional_edges( "content_review",
        route_after_review,
        {
            "content_review": "content_review",
            END: END,
        },
    )
    # ------------------------------------------------
    # 8. Compile with checkpointer
    logger.info("Compile graph with checkpointer")
    # ------------------------------------------------
    return workflow.compile(checkpointer = checkpointer)


