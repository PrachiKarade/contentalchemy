
"""Architecture page: ContentAlchemy's agent workflows as flowcharts.

Five diagrams (SEO blog, LinkedIn, Research, Image, Content strategist) show how the agents pass
information to each other and where the workflow pauses for the user (INTERRUPT). Hovering a box shows
what happens inside it. Mirrors src/core/workflow.py and the agent modules; keep them in sync.
"""

import streamlit as st

from src.web_app.components.flowchart import render_flowchart

# ---------------------------------------------------------------------------
# Shared nodes
# ---------------------------------------------------------------------------

QUERY_HANDLER_DETAILS = [
    "src/agents/query_handler.py",
    "One LLM call (text provider manager with automatic fallback) returns JSON.",
    "Extracts intent, topic, target audience, tone, keywords and objective.",
    "Values set in the sidebar Brand voice take priority over extracted ones.",
    "The intent routes the LangGraph to the right agent chain.",
]

RESEARCH_AGENT_DETAILS = [
    "src/agents/research_agent.py",
    "Queries SearchAPI and Perplexity for the topic and keywords.",
    "Streams progress: “Searching the web for sources…”, “Analyzing N sources…”.",
    "Keeps only valid source URLs.",
    "Saves the research draft to MongoDB.",
    "Writes research_results, research_summary and research_data to the state.",
]

SEARCHAPI_DETAILS = [
    "src/integrations/serp_client.py → search_web()",
    "Google results via SerpAPI (SERPAPI_KEY): title, URL and snippet.",
    "Up to 5 results per query; invalid URLs are dropped.",
]

PERPLEXITY_DETAILS = [
    "src/integrations/perplexity_client.py",
    "Asks Perplexity for an up-to-date, cited answer on the topic.",
    "Provides facts, statistics and supporting context.",
]

STRATEGIST_DETAILS = [
    "src/agents/content_strategist.py · prompts/content_strategist_prompt.py",
    "Combines the research with audience, tone, keywords and objective.",
    "Writes a research report and a content strategy: themes, key messages, angles, outline, CTA direction.",
    "Saves the combined draft to MongoDB.",
    "If it fails, the plain research report goes to review with a warning.",
]

CONTENT_REVIEW_DETAILS = [
    "src/agents/content_review.py · interrupt()",
    "Pauses the graph and shows the draft in the Chat and Content tabs.",
    "Options: Approve, Edit or Reject (buttons or typed reply).",
    "Edit → approval_status “edited” → the edited draft comes back for review.",
    "Approve → final_content is saved and the conversation is completed.",
    "Reject → the conversation is archived and a new one starts.",
]

BRAND_VOICE_DETAILS = [
    "src/core/brand_voice.py → build_brand_voice_context()",
    "Turns tone, audience and keywords into writing instructions.",
    "Asks the writer to use keywords naturally, without keyword stuffing.",
    "Empty when no preferences are set.",
]

MONGO_DRAFT_DETAILS = [
    "src/repositories/message_repository.py → add_message()",
    "message_type “generated_content”, status “draft”, version 1.",
    "The conversation moves to “awaiting_approval”.",
    "Lets the draft be reopened later from History.",
]


def query_handler(row: int, sub: str = "Detects intent and extracts context") -> dict:
    return {"row": row, "col": 1, "kind": "agent", "title": "Query Handler", "sub": sub, "details": QUERY_HANDLER_DETAILS}


def research_agent(row: int) -> dict:
    return {
        "row": row,
        "col": 1,
        "kind": "agent",
        "title": "Research Agent",
        "sub": "Gathers evidence on the topic",
        "details": RESEARCH_AGENT_DETAILS,
    }


def content_review(row: int, what: str = "draft") -> dict:
    return {
        "row": row,
        "col": 1,
        "kind": "interrupt",
        "title": "Content Review — INTERRUPT",
        "sub": f"You approve, edit or reject the {what}",
        "details": CONTENT_REVIEW_DETAILS,
    }


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

SEO_BLOG = {
    "nodes": {
        "user": {"row": 0, "col": 1, "kind": "input", "title": "User Blog Request", "sub": "Topic and goal from the chat",
                 "details": ["Typed in the Chat tab with SEO blog selected (or detected in Auto mode).",
                             "Starts a new conversation and LangGraph thread (thread_id = conversation_id)."]},
        "query": query_handler(1),
        "settings": {"row": 1, "col": 0, "kind": "side", "title": "Blog settings", "sub": "Audience · Tone · Keywords",
                     "details": ["From the sidebar Brand voice: Tone, Target audience, Target keywords.",
                                 "Optional; empty values let the assistant decide."]},
        "voice": {"row": 1, "col": 2, "kind": "side", "title": "Brand Voice Context", "sub": "Writing preferences",
                  "details": BRAND_VOICE_DETAILS},
        "research": research_agent(2),
        "serp": {"row": 3, "col": 0, "kind": "tool", "title": "SearchAPI", "sub": "SERP results and URLs", "details": SEARCHAPI_DETAILS},
        "perplexity": {"row": 3, "col": 1, "kind": "tool", "title": "Perplexity", "sub": "Research and supporting facts",
                       "details": PERPLEXITY_DETAILS},
        "output": {"row": 3, "col": 2, "kind": "tool", "title": "Research Output", "sub": "Findings and sources",
                   "details": ["research_results: list of sources (title, URL, snippet).",
                               "research_summary and research_data for the strategist."]},
        "strategist": {"row": 4, "col": 1, "kind": "agent", "title": "Content Strategist", "sub": "Research report + content strategy",
                       "details": STRATEGIST_DETAILS},
        "generator": {"row": 5, "col": 1, "kind": "agent", "title": "SEO Blog Generator", "sub": "Writes the full article",
                      "details": ["src/agents/content_generator.py → generate_seo_blog_from_strategy()",
                                  "Uses the strategy, research report, blog settings and brand voice.",
                                  "LLM returns JSON: SEO title, meta description, URL slug, keywords, outline, FAQs, CTA, sources, article.",
                                  "The article streams live to the Content tab while it is written.",
                                  "Source URLs are checked against the research results.",
                                  "Text provider fallback switches LLM provider if one fails."]},
        "draft": {"row": 6, "col": 1, "kind": "agent", "title": "Generated SEO Blog Draft", "sub": "Formatted Markdown article",
                  "details": ["format_blog_markdown() turns the JSON into a readable article.",
                              "Shown in the Content tab for review."]},
        "mongo": {"row": 7, "col": 1, "kind": "store", "title": "MongoDB — Save Draft", "sub": "Draft message and status",
                  "details": MONGO_DRAFT_DETAILS},
        "review": content_review(8, "blog"),
        "outcome": {"row": 9, "col": 1, "kind": "result", "title": "Approved / Edited / Rejected",
                    "details": ["Approved: download as Markdown from the Content tab or Content dashboard.",
                                "Edited: your version is reviewed again, then approved.",
                                "Rejected: archived; a new conversation starts."]},
    },
    "edges": [
        {"from": "user", "to": "query", "label": "Request details"},
        {"from": "query", "to": "research", "label": "Topic · intent · audience · keywords"},
        {"from": "research", "to": "serp"},
        {"from": "research", "to": "perplexity"},
        {"from": "research", "to": "output"},
        {"from": "serp", "to": "strategist", "dx": -50},
        {"from": "perplexity", "to": "strategist", "label": "Research report · sources", "label_pos": "upper"},
        {"from": "output", "to": "strategist", "dx": 50},
        {"from": "strategist", "to": "generator", "label": "Research report · strategy"},
        {"from": "settings", "to": "generator", "route": "side", "label": "Audience · tone · keywords"},
        {"from": "voice", "to": "generator", "route": "side", "label": "Writing preferences"},
        {"from": "generator", "to": "draft", "label": "Article JSON (streamed)"},
        {"from": "draft", "to": "mongo"},
        {"from": "mongo", "to": "review", "label": "Draft message and review status"},
        {"from": "review", "to": "review", "label": "Edit → review again"},
        {"from": "review", "to": "outcome", "label": "Decision"},
    ],
}

LINKEDIN = {
    "nodes": {
        "user": {"row": 0, "col": 1, "kind": "input", "title": "User LinkedIn Request", "sub": "What to post about",
                 "details": ["Typed in the Chat tab with LinkedIn post selected (or detected in Auto mode)."]},
        "query": query_handler(1),
        "profile": {"row": 2, "col": 1, "kind": "interrupt", "title": "LinkedIn Profile Interaction — INTERRUPT",
                    "sub": "You share identity, role, objective, experience and tone",
                    "details": ["src/agents/linkedin_interaction.py · interrupt() per question",
                                "Up to 5 questions, one at a time: professional identity, current role, LinkedIn objective, experience level, preferred tone.",
                                "Pick one or more options, or type your own (Other).",
                                "Questions already answered in your saved profile are skipped.",
                                "Answers are saved to your profile for next time."]},
        "saved": {"row": 2, "col": 2.03, "kind": "side", "width": 150, "title": "Saved profile", "sub": "MongoDB",
                  "details": ["src/repositories/profile_repository.py",
                              "Remembers earlier answers so you aren't asked twice."]},
        "research": research_agent(3),
        "strategist": {"row": 4, "col": 1, "kind": "agent", "title": "Content Strategist", "sub": "Audience angle · message · CTA direction",
                       "details": STRATEGIST_DETAILS},
        "writer": {"row": 5, "col": 1, "kind": "agent", "title": "LinkedIn Writer", "sub": "Hook · Post · Hashtags · CTA",
                   "details": ["src/agents/linkedin_writer.py → write_linkedin_post()",
                               "Called by the content generator with the strategy, research and profile answers.",
                               "Returns hook, post body, call to action and hashtags.",
                               "Tone comes from your profile answers.",
                               "Text provider fallback switches LLM provider if one fails."]},
        "review": content_review(6, "post"),
        "mongo": {"row": 7, "col": 1, "kind": "store", "title": "MongoDB — Save Final Status", "sub": "Final content and conversation status",
                  "details": ["Approved: final_content message saved, conversation “completed”.",
                              "Rejected: conversation “archived”."]},
        "result": {"row": 8, "col": 1, "kind": "result", "title": "Return Result to Streamlit", "sub": "Content tab and dashboard",
                   "details": ["The workflow resumes and streams events back to the UI.",
                               "The approved post appears in the Content tab and Content dashboard."]},
    },
    "edges": [
        {"from": "user", "to": "query"},
        {"from": "query", "to": "profile", "label": "LinkedIn intent · topic"},
        {"from": "saved", "to": "profile", "route": "across"},
        {"from": "profile", "to": "research", "label": "Profile answers"},
        {"from": "research", "to": "strategist", "label": "Research findings and sources"},
        {"from": "strategist", "to": "writer", "label": "Strategy and writing direction"},
        {"from": "writer", "to": "review", "label": "Generated post draft"},
        {"from": "review", "to": "review", "label": "Edit → review again"},
        {"from": "review", "to": "mongo", "label": "Review decision and edited content"},
        {"from": "mongo", "to": "result"},
    ],
}

RESEARCH = {
    "nodes": {
        "query": query_handler(0),
        "research": {**research_agent(1), "sub": "Searches and synthesizes evidence"},
        "serp": {"row": 2, "col": 0, "kind": "tool", "title": "SearchAPI", "sub": "SERP results", "details": SEARCHAPI_DETAILS},
        "perplexity": {"row": 2, "col": 1, "kind": "tool", "title": "Perplexity", "sub": "Research answers", "details": PERPLEXITY_DETAILS},
        "sources": {"row": 2, "col": 2, "kind": "tool", "title": "Source URLs", "sub": "Supporting references",
                    "details": ["Collected from the search results and citations.",
                                "is_valid_source_url() drops broken or unsafe links."]},
        "output": {"row": 3, "col": 1, "kind": "agent", "title": "Research Output", "sub": "Results · Summary · Report · Sources",
                   "details": ["research_results, research_summary, research_data.",
                               "Saved as a draft message in MongoDB."]},
        "strategist": {"row": 4, "col": 1, "kind": "agent", "title": "Content Strategist", "sub": "Research report + content strategy",
                       "details": STRATEGIST_DETAILS},
        "review": content_review(5, "report"),
    },
    "edges": [
        {"from": "query", "to": "research", "label": "Topic · keywords · audience · research intent"},
        {"from": "research", "to": "serp"},
        {"from": "research", "to": "perplexity"},
        {"from": "research", "to": "sources"},
        {"from": "serp", "to": "output", "dx": -50},
        {"from": "perplexity", "to": "output", "label": "Consolidated findings and sources", "label_pos": "upper"},
        {"from": "sources", "to": "output", "dx": 50},
        {"from": "output", "to": "strategist", "label": "Research data"},
        {"from": "strategist", "to": "review", "label": "Report + strategy"},
        {"from": "review", "to": "review", "label": "Edit → review again"},
    ],
}

IMAGE = {
    "nodes": {
        "user": {"row": 0, "col": 1, "kind": "input", "title": "User Image Request", "sub": "Describe the image you want",
                 "details": ["Typed in the Chat tab with Image selected (or detected in Auto mode)."]},
        "prefs": {"row": 1, "col": 1, "kind": "interrupt", "title": "Image Preference Interaction — INTERRUPT",
                  "sub": "Asks only for missing preferences",
                  "details": ["src/agents/image_preferences.py",
                              "The request analyzer first fills preferences your request already states (e.g. “landscape banner”).",
                              "Then asks, one at a time: purpose, visual style, orientation, quality.",
                              "Unclear answers are asked again with a hint.",
                              "Skipped entirely when the request covers all four."]},
        "prompt": {"row": 2, "col": 1, "kind": "agent", "title": "Image Prompt / Direction", "sub": "Subject · style · visual preferences",
                   "details": ["src/agents/image_generator.py",
                               "The LLM crafts a detailed image prompt from the request and preferences.",
                               "Orientation sets the size: square 1024×1024, portrait 1024×1792, landscape 1792×1024."]},
        "generator": {"row": 3, "col": 1, "kind": "agent", "title": "Image Generation Agent", "sub": "Creates the image with the selected provider",
                      "details": ["src/integrations/image_provider_manager.py",
                                  "Tries the primary provider, then the fallbacks.",
                                  "The image is stored via image_storage (Azurite blob or local file).",
                                  "If every provider fails, the workflow ends with an error message."]},
        "providers": {"row": 3, "col": 0, "kind": "side", "title": "Image providers", "sub": "Stability → OpenAI → Gemini",
                      "details": ["Primary: Stability AI.", "Fallbacks: OpenAI, then Gemini.",
                                  "Configured with environment variables."]},
        "review": {"row": 4, "col": 1, "kind": "interrupt", "title": "Image Review — INTERRUPT", "sub": "You review and choose the next action",
                   "details": ["src/agents/image_review.py · interrupt()",
                               "Approve: the image is final and can be downloaded.",
                               "Edit prompt: generate again from your new prompt.",
                               "Regenerate: a new image from the same prompt.",
                               "Reject: archived; a new conversation starts."]},
        "result": {"row": 5, "col": 1, "kind": "result", "title": "Return Image to Streamlit", "sub": "Download from the Chat or Content tab",
                   "details": ["The approved image is saved to MongoDB and shown in the Content dashboard."]},
    },
    "edges": [
        {"from": "user", "to": "prefs"},
        {"from": "prefs", "to": "prefs", "label": "Until all 4 set"},
        {"from": "prefs", "to": "prompt", "label": "Confirmed preferences"},
        {"from": "prompt", "to": "generator", "label": "Image prompt and size"},
        {"from": "providers", "to": "generator", "route": "across"},
        {"from": "generator", "to": "review", "label": "Generated image"},
        {"from": "review", "to": "generator", "label": "Edit / Regenerate"},
        {"from": "review", "to": "result", "label": "Approve"},
    ],
}

CONTENT_STRATEGIST = {
    "nodes": {
        "research": {"row": 0, "col": 0, "kind": "agent", "width": 240, "title": "Research Agent", "sub": "Research report + findings",
                     "details": RESEARCH_AGENT_DETAILS},
        "prefs": {"row": 0, "col": 1, "kind": "agent", "width": 240, "title": "User Preferences", "sub": "Audience · tone · keywords · goal",
                  "details": ["From the Query Handler and the sidebar Brand voice.",
                              "target_audience, tone, keywords, objective."]},
        "voice": {"row": 0, "col": 2, "kind": "side", "width": 240, "title": "Brand Voice Context", "sub": "Writing preferences",
                  "details": BRAND_VOICE_DETAILS},
        "strategist": {"row": 1.25, "col": 1, "kind": "agent", "title": "Content Strategist", "sub": "Combines research and user context",
                       "details": STRATEGIST_DETAILS},
        "blog": {"row": 2.5, "col": 0.5, "kind": "agent", "width": 240, "title": "SEO Blog Writer", "sub": "Blog angle · outline · CTA",
                 "details": ["Content generator, blog branch.", "Uses the strategy's outline and keywords."]},
        "linkedin": {"row": 2.5, "col": 1.5, "kind": "agent", "width": 240, "title": "LinkedIn Writer", "sub": "Post angle · hook · CTA",
                     "details": ["Content generator, LinkedIn branch.", "Uses the strategy's angle and key message."]},
        "review": {**content_review(3.75, "report"), "width": 250, "title": "Content Review",
                   "sub": "Research requests go straight to review"},
    },
    "edges": [
        {"from": "research", "to": "strategist", "dx": -60},
        {"from": "prefs", "to": "strategist", "label": "Inputs to strategy", "label_pos": "upper"},
        {"from": "voice", "to": "strategist", "dx": 60},
        {"from": "strategist", "to": "blog", "label": "Strategy and content direction", "label_at": (130, 200)},
        {"from": "strategist", "to": "linkedin"},
        {"from": "strategist", "to": "review", "label": "Research intent", "label_at": (410, 326)},
    ],
}

WORKFLOWS = {
    "blog": {"name": "SEO Blog", "icon": ":material/article:", "summary": "Research, strategy, then a streamed SEO article.",
             "diagram": SEO_BLOG},
    "linkedin": {"name": "LinkedIn", "icon": ":material/work:", "summary": "Profile questions, then a tailored post.",
                 "diagram": LINKEDIN},
    "research": {"name": "Research Agent", "icon": ":material/travel_explore:", "summary": "Web research fanned out to sources.",
                 "diagram": RESEARCH},
    "image": {"name": "Image", "icon": ":material/image:", "summary": "Preferences, generation, review loop.",
              "diagram": IMAGE},
    "strategist": {"name": "Content Strategist", "icon": ":material/psychology:", "summary": "How research becomes a content plan.",
                   "diagram": CONTENT_STRATEGIST},
}


# Short description shown above each workflow: what the agent does, what you give it, what you get.
ABOUT = {
    "blog": {
        "what": "Writes long-form, search-optimized blog articles. It researches your topic on the web, plans the "
        "article with the Content Strategist, then writes it while you watch it stream in the Content tab.",
        "give": "A topic, plus optional tone, audience and keywords in the sidebar.",
        "get": "A full article with SEO title, meta description, outline, FAQs and sources, ready to download.",
    },
    "linkedin": {
        "what": "Writes LinkedIn posts that sound like you. It first learns your professional profile with a few "
        "quick questions (asked once, then remembered), researches the topic and drafts the post.",
        "give": "What you want to post about, and answers to up to 5 profile questions.",
        "get": "A post with a strong hook, body, call to action and hashtags.",
    },
    "research": {
        "what": "Researches a topic across the web. It queries SearchAPI and Perplexity in parallel, keeps only "
        "valid sources, and turns the findings into a research report with a content strategy.",
        "give": "A topic or question to research.",
        "get": "A research report with cited sources, followed by a content strategy.",
    },
    "image": {
        "what": "Creates marketing images. It asks only for the preferences your request leaves out, crafts a "
        "detailed prompt and generates the image, falling back to another provider if one fails.",
        "give": "A description of the image, and any missing purpose, style, orientation or quality.",
        "get": "An image you can approve, refine, regenerate and download.",
    },
    "strategist": {
        "what": "The planning agent shared by the SEO blog, LinkedIn and Research workflows. It combines the research "
        "with your preferences and brand voice into a content strategy the writers follow.",
        "give": "Nothing directly: it receives the research and your preferences from the other agents.",
        "get": "A research report and a content strategy: themes, key messages, angles, outline and CTA direction.",
    },
}


def render_about(workflow: str) -> None:
    info, about = WORKFLOWS[workflow], ABOUT[workflow]
    with st.container(border=True, key="agent_about"):
        st.markdown(f"#### {info['icon']} {info['name']}")
        st.markdown(about["what"])
        give, get = st.columns(2)
        with give:
            st.markdown(f"**:material/input: You provide**  \n{about['give']}")
        with get:
            st.markdown(f"**:material/output: You get**  \n{about['get']}")


def interrupt_count(diagram: dict) -> int:
    return sum(1 for node in diagram["nodes"].values() if node["kind"] == "interrupt")


def select_workflow(workflow: str) -> None:
    st.session_state["architecture_selected"] = workflow


def render_overview() -> None:
    cards = [
        (":material/hub:", "LangGraph orchestrator", "Routes each request by intent to the right chain of agents."),
        (":material/database:", "Shared state", "Agents talk through one ContentState: each reads fields and writes new ones."),
        (":material/pause_circle:", "Interrupts", "The graph pauses for your answers or review, then resumes where it stopped."),
        (":material/save:", "Checkpoints and storage", "Each conversation is a checkpointed thread; drafts and results go to MongoDB."),
    ]
    columns = st.columns(len(cards))
    for column, (icon, title, text) in zip(columns, cards):
        with column, st.container(border=True, key=f"arch_overview_{title.split()[0].lower()}", height="stretch"):
            st.markdown(f"**{icon} {title}**")
            st.caption(text)


def render_workflow_picker(selected: str) -> None:
    columns = st.columns(len(WORKFLOWS))
    for column, (workflow, info) in zip(columns, WORKFLOWS.items()):
        key = "agent_card_selected" if workflow == selected else f"agent_card_{workflow}"
        with column, st.container(border=True, key=key, height="stretch"):
            st.markdown(f"**{info['icon']} {info['name']}**")
            st.caption(info["summary"])
            pauses = interrupt_count(info["diagram"])
            st.caption(f":material/pause_circle: {pauses} interrupt{'s' if pauses != 1 else ''}")
            st.button(
                "Viewing" if workflow == selected else "View",
                icon=":material/account_tree:",
                type="primary" if workflow == selected else "secondary",
                width="stretch",
                key=f"agent_view_{workflow}",
                on_click=select_workflow,
                args=(workflow,),
            )


def render_legend() -> None:
    items = [
        ("input", "User"), ("agent", "Agent"), ("tool", "Tool / data source"), ("side", "Settings input"),
        ("interrupt", "INTERRUPT · waits for you"), ("store", "MongoDB"), ("result", "Result"),
    ]
    swatches = "".join(
        f'<span class="ca-fc-legend-item"><span class="ca-fc-swatch ca-fc-{kind}"></span>{label}</span>'
        for kind, label in items
    )
    st.html(f'<div class="ca-fc-legend">{swatches}<span class="ca-fc-legend-item">ⓘ Hover a box for details</span></div>')


def render_architecture() -> None:
    st.markdown("### Architecture")
    st.caption(
        "How ContentAlchemy's agents work together: what each one passes to the next, "
        "and where the workflow pauses for you. Hover any box to see what happens inside it."
    )
    render_overview()

    selected = st.session_state.get("architecture_selected", "blog")
    if selected not in WORKFLOWS:
        selected = "blog"
    render_workflow_picker(selected)

    # What the agent does first, then its workflow.
    render_about(selected)
    with st.container(border=True, key="agent_diagram"):
        st.markdown(f"**:material/account_tree: {WORKFLOWS[selected]['name']} workflow**")
        render_legend()
        st.html(render_flowchart(WORKFLOWS[selected]["diagram"]))
