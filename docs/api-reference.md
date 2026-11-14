# ContentAlchemy — API Reference

ContentAlchemy has **no HTTP API**. Its interfaces are:

1. The **application API** in `src/web_app/assistant.py`, which the Streamlit UI calls.
2. The compiled **LangGraph graph** (`src/core/workflow.py`): nodes, state, interrupt payloads and resume values.
3. The **agent functions** that can be called without the graph.
4. **Integration interfaces**: text and image provider managers, search, storage.
5. **Repositories**: MongoDB data access.

All signatures below are taken from the source. Imports assume the project root is on `sys.path` (as
`streamlit_app.py` arranges).

---

## 1. Application API — `src/web_app/assistant.py`

### 1.1 Constants

| Name | Value / meaning |
|---|---|
| `DEFAULT_USER_ID` | `"usr_local_001"` (overridden by `CONTENTALCHEMY_USER_ID`) |
| `CONTENT_TYPES` | UI content types: `auto`, `research`, `blog`, `linkedin`, `image`, `multi`, `strategy`, `chat` (label, icon, colour) |
| `REPO_TYPES` | `{"blog": "seo_blog"}`: the UI type `blog` is stored as `seo_blog` in MongoDB |
| `ROUTING_KEYWORDS` | Auto mode: `linkedin` → linkedin · `blog`/`article`/`seo` → blog · `image`/`banner`/`illustration`/`picture`/`graphic`/`visual` → image · `research`/`trends`/`report`/`analyze`/`analysis` → research |
| `MULTI_STEP_NODES` | Nodes a multi-content thread pauses after (`interrupt_after`) so the UI can render each step |
| `HISTORY_LIMIT` | `6` previous turns included in general chat |

### 1.2 Users, history and dashboard

```python
get_current_user() -> dict                       # {"user_id", "username"}; cached 10 min
list_history(user_id: str) -> list[dict]         # ≤ 30 conversations, newest first; [] if MongoDB is down
refresh_history() -> None                        # clears the history and dashboard caches
list_approved_content(user_id: str) -> list[dict]
save_approved_content(user_id: str, item: dict, body: str) -> None
remove_approved_content(user_id: str, conversation_id: str) -> None   # archives the conversation
load_conversation(user_id: str, conversation_id: str) -> tuple[dict, list[dict]]   # (conversation, ≤ 200 messages)
detect_content_type(prompt: str) -> str | None   # Auto-mode keyword routing; None means general chat
```

`list_approved_content` returns one item per completed conversation (one per deliverable for multi-content):

```python
{
  "id": "conv_…" | "conv_…:blog",   # multi items are suffixed with the deliverable type
  "conversation_id": "conv_…",      # multi items only
  "message_id": "msg_…",            # the final_content message
  "type": "blog" | "linkedin" | "research" | "image" | "strategy",
  "title": str, "prompt": str, "body": str,
  "data": dict,                     # structured generated_content (e.g. blog SEO fields)
  "strategy": str,                  # single conversations only
  "metadata": dict, "created_at": datetime,
}
```

### 1.3 Running content workflows

```python
start_agent(
    user_id: str,
    content_type: str,            # "research" | "blog" | "linkedin" | "image" | "multi"
    request: str,
    settings: dict,               # {"audience": str, "tone": str, "keywords": "comma, separated"}
    on_step: Callable[[str], None] | None = None,    # human-readable step label per finished node
    on_event: Callable[[dict], None] | None = None,  # custom stream events (see §2.5)
) -> tuple[str, dict | None, dict]                   # (conversation_id, interrupt payload or None, state)
```

Creates the conversation and a `request` message, then runs the graph until it pauses or ends. When it ends because
image generation failed, it records an `error` message and marks the conversation `failed`.

```python
answer_question(user_id, conversation_id, content_type, response: dict, answer_text: str,
                on_step=None, on_event=None) -> tuple[dict | None, dict]
```

Resumes a pending **question** interrupt (LinkedIn profile, image preference). `response` is the resume value (§2.4);
`answer_text` is what gets stored as the `answer` message.

```python
submit_decision(user_id, conversation_id, content_type, draft: str,
                action: str,               # "approve" | "edit" | "reject"
                edited_content: str = "") -> tuple[dict | None, dict]
```

Resumes `content_review`. An **edit** returns a new review payload (the edited draft, re-scored). **Approve** stores a
`final_content` message and marks the conversation `completed`; **reject** archives it. If the checkpoint is gone (app
restarted), the same rules are applied without the graph.

```python
submit_image_decision(user_id, conversation_id,
                      action: str,          # "approve" | "edit" | "regenerate" | "reject"
                      edited_prompt: str = "",
                      image: dict | None = None,   # {"path", "prompt", "message_id"}; used when the checkpoint is gone
                      on_step=None, on_event=None) -> tuple[dict | None, dict]
```

Resumes `image_review`. **Edit** and **regenerate** return a new `image_review` payload. Without a checkpoint, only
approve and reject are allowed (`ValueError` otherwise).

### 1.4 Multi-content (step-wise)

```python
advance_multi(user_id, conversation_id,
              value: dict | Command | None,   # initial state, Command(resume=…), or None to continue
              on_step=None, on_event=None) -> tuple[dict | None, dict, tuple[str, ...]]
# returns (payload, state, next_nodes)
#   payload       → an agent is waiting for the user
#   no payload, next_nodes empty → workflow ended; approved pieces are saved (finalize_multi)
#   otherwise     → call again with None
build_multi_decision(deliverable: str, action: str, edited_content: str = "", edited_prompt: str = "") -> dict
record_multi_answer(user_id, conversation_id, answer_text: str) -> None
record_multi_review(user_id, conversation_id, deliverable: str, decision: dict) -> None
finalize_multi(user_id, conversation_id, state: dict) -> None
```

### 1.5 Thread inspection and low-level runner

```python
get_workflow()                                       # compiled graph with MemorySaver (cached per process)
thread_config(conversation_id) -> {"configurable": {"thread_id": conversation_id}}
get_pending_payload(conversation_id) -> dict | None  # value of the pending interrupt
get_thread_state(conversation_id) -> dict            # {} if the checkpoint is gone
get_next_nodes(conversation_id) -> tuple[str, ...]
run_workflow(conversation_id, value: dict | Command, on_step=None, on_event=None,
             interrupt_after: list[str] | None = None) -> tuple[dict | None, dict]
```

`run_workflow` streams with `stream_mode=["updates", "custom"]`. Custom events go to `on_event`, node updates are
mapped to labels for `on_step`, and `__interrupt__` updates become the returned payload.

### 1.6 General chat

```python
chat_reply(prompt: str, history: list[dict]) -> str            # OpenAI directly (no fallback)
save_chat_turn(user_id, conversation_id: str | None, prompt: str, reply: str) -> str | None
```

### 1.7 End-to-end example

```python
from langgraph.types import Command
from src.web_app.assistant import (
    get_current_user, start_agent, answer_question, submit_decision, advance_multi,
)

user_id = get_current_user()["user_id"]
settings = {"audience": "Developers", "tone": "Professional", "keywords": "LangGraph, agents"}

# LinkedIn: 5 profile questions, then a review
cid, payload, state = start_agent(user_id, "linkedin", "Post about building agents with LangGraph", settings)
while payload and payload["interaction_type"] == "linkedin_profile_question":
    first = payload["options"][0]
    payload, state = answer_question(
        user_id, cid, "linkedin",
        response={"selected_options": [first], "other_text": ""},
        answer_text=first,
    )

assert payload["interaction_type"] == "content_review"
print(payload["quality"])   # {"score": 82, "grade": "Good", "checks": {...}, "suggestions": [...]}
submit_decision(user_id, cid, "linkedin", draft=payload["content"], action="approve")
```

---

## 2. LangGraph graph — `src/core/workflow.py`

```python
from src.core.workflow import build_workflow
from langgraph.checkpoint.memory import MemorySaver

graph = build_workflow(checkpointer=MemorySaver())   # a checkpointer is required for interrupts
config = {"configurable": {"thread_id": "conv_…"}}   # must match an existing MongoDB conversation
```

Most nodes load the conversation from MongoDB (`get_conversation(conversation_id, user_id)`), so the conversation must
exist first (`create_conversation`). For the research agent, its `content_type` must be one of `research`,
`linkedin`, `seo_blog` or `multi`.

### 2.1 Initial state

The state `assistant.create_content_conversation` passes to `graph.stream()`:

```python
{
  "user_id": "usr_local_001",
  "conversation_id": "conv_…",
  "intent": "blog",              # optional: if set it overrides the query handler's classification
  "user_request": "Write an SEO blog about …",
  "target_audience": "Marketers",
  "tone": "Professional",
  "keywords": ["AI", "B2B"],
  "completed_agents": [],
  "errors": [],
  # optional: "requested_agents": ["blog", "linkedin", "image"], "objective": "…",
  #           "image_purpose" / "image_visual_style" / "image_orientation" / "image_quality"
}
```

### 2.2 Nodes

| Node | Function | Pauses |
|---|---|---|
| `query_handler` | `agents.query_handler.query_handler_node` | |
| `linkedin_profile_interaction` | `agents.linkedin_interaction.linkedin_profile_interaction_node` | ×5 |
| `research_agent` | `agents.research_agent.research_agent_node` | |
| `content_strategist` | `agents.content_strategist.content_strategist_node` | |
| `content_generator` | `agents.content_generator.content_generator_node` | |
| `content_review` | `agents.content_review.content_review_node` | ×1 |
| `image_request_analyzer` | `agents.image_preferences.image_request_analyzer_node` | |
| `image_preference_interaction` | `agents.image_preferences.image_preference_interaction_node` | ×1 per run |
| `image_generator` | `agents.image_generator.image_generator_node` | |
| `image_review` | `agents.image_review.image_review_node` | ×1 |
| `multi_agent_orchestrator` | `agents.multi_agent_orchestrator.multi_agent_orchestrator_node` | |
| `multi_content_generator` | `agents.content_generator.multi_content_generator_node` | |
| `multi_content_review` | `agents.content_review.multi_content_review_node` | ×1 per text deliverable |

Routing rules are in the [Technical Design Document §3.2](technical-design-document.md#32-routers).

### 2.3 Interrupt payloads

The value of `snapshot.interrupts[0].value`, also returned by `run_workflow`.

**LinkedIn profile question**

```python
{
  "interaction_type": "linkedin_profile_question",
  "lookup_key": "professional_identity",   # | current_role | linkedin_objective | experience_level | preferred_tone
  "question": "How would you describe yourself professionally?",
  "options": ["Software Developer", "Backend Developer", …, "Other"],
  "selection_type": "multiple",
  "allow_other": True,
}
```

**Image preference question**

```python
{
  "interaction_type": "image_preference_question",
  "agent": "image_generator",
  "lookup_key": "image_purpose",           # | image_visual_style | image_orientation | image_quality
  "question": "What will you use this image for?",   # prefixed with an error message after an invalid answer
  "options": ["Blog article", "LinkedIn post", "Website", "Presentation", "Marketing campaign", "Other"],
  "selection_type": "single",
  "allow_other": True,
  "is_last": False,                        # True for the last missing preference
}
```

| `lookup_key` | Options | Accepted free text |
|---|---|---|
| `image_purpose` | Blog article, LinkedIn post, Website, Presentation, Marketing campaign, Other | any |
| `image_visual_style` | Photorealistic, 3D illustration, Minimalist, Cinematic, Vector art, Watercolor, Other | any |
| `image_orientation` | Square, Portrait, Landscape | square / 1:1 / instagram · portrait / vertical / tall / story / 9:16 · landscape / horizontal / wide / banner / 16:9 |
| `image_quality` | Standard, HD | standard / normal / regular / default / basic · hd / high / detailed / best / premium |

**Content review** (single and multi)

```python
{
  "interaction_type": "content_review",
  "content_type": "blog",                  # intent, or the deliverable in multi mode
  "agent": "content_generator",
  "question": "Please review your generated blog content.",
  "content": "# Title\n…",                 # Markdown shown to the reviewer
  "quality": {"score": 78, "grade": "Good", "checks": {...}, "suggestions": [...]} | None,
  "options": ["approve", "edit", "reject"],
  # multi only:
  "deliverable": "blog", "multi": True,
}
```

**Image review**

```python
{
  "interaction_type": "image_review",
  "agent": "image_generator",
  "question": "Please review your generated image.",
  "content": "<image_path>",
  "image_prompt": "<enhanced prompt>",
  "options": ["approve", "edit", "regenerate", "reject"],
  "status": "pending",
}
```

### 2.4 Resume values (`Command(resume=…)`)

| Interrupt | Resume value | Validation |
|---|---|---|
| `linkedin_profile_question` | `{"selected_options": list[str] \| str, "other_text": str}` | At least one answer besides "Other", else `ValueError` |
| `image_preference_question` | `{"selected_options": list[str] \| str, "other_text": str}` | First answer is normalised; an invalid answer asks again |
| `content_review` | `{"action": "approve" \| "edit" \| "reject", "edited_content": str}` | `edited_content` required for `edit` |
| `image_review` | `{"action": "approve" \| "edit" \| "regenerate" \| "reject", "edited_prompt": str}` | `edited_prompt` required for `edit` |

```python
from langgraph.types import Command
for mode, update in graph.stream(Command(resume={"action": "approve"}), config,
                                 stream_mode=["updates", "custom"]):
    ...
```

### 2.5 Custom stream events (`stream_mode="custom"`)

Emitted with `get_stream_writer()` and delivered to `on_event`:

| Event | Emitted by | Example |
|---|---|---|
| `{"event": "status", "text": …}` | research, blog writer, image analyzer and generator | `"Searching the web for sources..."`, `"Analyzing 5 sources..."`, `"Writing your SEO blog..."`, `"Crafting a detailed image prompt..."`, `"Generating your image (this can take up to a minute)..."` |
| `{"event": "text", "text": …}` | SEO blog writer | Incremental chunks of `blog_article` |

### 2.6 Key output fields

| Field | Set by | Meaning |
|---|---|---|
| `current_content` | research, strategist, generators, review | The text shown in the next review |
| `generated_content_message_id` | research, strategist, generator | MongoDB message the review updates |
| `approval_status` | `content_review` | `approved` · `edited` · `rejected` |
| `final_content` | `content_review` | Approved text (empty unless approved) |
| `quality_score` / `quality_grade` / `quality_details` / `quality_suggestions` | generator, review (edits) | Quality score (§4.4) |
| `image_status` | image nodes | `pending` · `generated` · `approved` · `rejected` · `failed` |
| `image_error` | `image_generator` | User-facing failure message |
| `multi_agent_results` | strategist, multi generator, multi review, image review | Per-deliverable results (see the design doc §4.3) |
| `errors` | image generator | Failure messages |

The full field list is in `src/core/state.py` and the [Technical Design Document §4](technical-design-document.md#4-state-management).

---

## 3. Agent functions (usable without the graph)

```python
from src.agents.query_handler import analyze_query
analyze_query(user_request: str) -> QueryAnalysis
# {"intent", "topic", "target_audience", "tone", "keywords", "objective", "requested_agents"}
# Raises pydantic.ValidationError or ValueError("Query Handler returned invalid JSON.")

from src.agents.research_agent import research_topic, format_research_report
research_topic(topic: str, target_audience: str = "", num_results: int = 5,
               on_event: Callable[[dict], None] | None = None) -> dict
# {"topic", "research_summary", "findings": [{"claim", "explanation", "source_urls"}],
#  "sources": [{"title", "url", "snippet"}]}, validated and grounded in the search results
format_research_report(research_data: dict) -> str   # Markdown; the UI parses its headings

from src.agents.linkedin_writer import write_linkedin_post
write_linkedin_post(topic: str, profile_answers: dict, target_audience: str = "", tone: str = "Professional",
                    keywords: list[str] | None = None, objective: str = "", research_report: str = "",
                    content_strategy: str = "", brand_voice_context: str = "") -> dict
# {"hook", "post_body", "hashtags": ["#tag", …], "call_to_action"}

from src.agents.content_generator import generate_seo_blog_from_strategy
generate_seo_blog_from_strategy(topic, research_report, content_strategy, target_audience="", tone="",
                                keywords=None, objective="", available_results=None,
                                brand_voice_context="", on_event=None) -> dict
# {"seo_title", "meta_description", "url_slug", "primary_keyword", "secondary_keywords",
#  "search_intent", "article_outline": [{"level", "heading"}], "faqs": [{"question", "answer"}],
#  "call_to_action", "sources": [{"title", "url"}], "blog_article"}

from src.agents.image_preferences import extract_image_preferences, normalize_preference
extract_image_preferences(user_request: str) -> dict   # only the preferences found; {} on any failure
normalize_preference(key: str, value) -> str | None

from src.core.brand_voice import build_brand_voice_context
build_brand_voice_context(state: dict) -> str          # "WRITING PREFERENCES: …" or ""
```

---

## 4. Integration interfaces

### 4.1 Text — `src/integrations/text_provider_manager.py`

```python
from src.integrations.text_provider_manager import text_provider_manager   # module-level singleton

text_provider_manager.generate_text(query: str, system_prompt: str | None = None,
                                    model: str | None = None, max_output_tokens: int | None = None) -> str
text_provider_manager.stream_text(query, system_prompt=None, model=None, max_output_tokens=None) -> Iterator[str]
text_provider_manager.provider_order  # e.g. ["openai", "claude", "gemini", "perplexity"]
```

- Raises `TextProviderManagerError` (with `.failures: list[tuple[provider, reason]]`) when every provider fails.
- `model=` is passed to whichever provider runs, so leave it `None` unless you pin a provider.
- `MAX_RETRIES = 2`, `BASE_RETRY_DELAY = 1` s (exponential backoff), retryable errors only.

Every provider module (`openai_client`, `claude_client`, `gemini_client`, `perplexity_client`) exposes the same two
functions:

```python
generate_text(query: str, system_prompt: str | None = None, model: str | None = None,
              max_output_tokens: int | None = None) -> str
stream_text(query: str, system_prompt: str | None = None, model: str | None = None,
            max_output_tokens: int | None = None) -> Iterator[str]
```

Error taxonomy (`providers/text/text_provider_errors.py`):

| Class | `retryable` |
|---|---|
| `TextProviderError` (base) | as given |
| `TextProviderRateLimitError` | `True` |
| `TextProviderTemporaryError` | `True` |
| `TextProviderQuotaError` | `False` |
| `TextProviderAccessError` | `False` |
| `TextProviderRequestError` | `False` |

To add a text provider, create a module with `generate_text` and `stream_text` that raise these errors, then register
it in `TextProviderManager.PROVIDERS`.

### 4.2 Images

```python
from src.integrations.image_clients import generate_image
generate_image(prompt: str, conversation_id: str, quality: str = "standard",   # "standard" | "hd"
               size: str = "1024x1024",          # "1024x1024" | "1024x1792" | "1792x1024"
               style: str = "vivid") -> dict
# {"image_path", "image_url", "revised_prompt": None, "provider"}
# See the known storage defect in technical-design-document.md §8.4

from src.integrations.image_provider_manager import ImageProviderManager
ImageProviderManager().generate_image(prompt: str, size: str = "1024x1024") -> {"provider": str, "image_bytes": bytes}
```

Every image provider implements `generate(prompt: str, size: str = "1024x1024") -> bytes` and has a `name`. Errors
(`providers/images/provider_errors.py`): `ImageProviderError` (base), `InsufficientCreditsError`,
`ProviderAccessError`, `ProviderRateLimitError`, `ProviderTemporaryError`.

### 4.3 Search — `src/integrations/serp_client.py`

```python
search_web(query: str, num_results: int = 5) -> list[dict]   # [{"title", "url", "snippet"}]; [] if all fail
search_google(query: str, num_results: int) -> list[dict]    # SerpApi; [] without SERPAPI_KEY
search_tavily(query: str, num_results: int) -> list[dict]    # Tavily;  [] without TAVILY_API_KEY
is_valid_source_url(url: str) -> bool                        # http(s), not google.com
```

`num_results` is clamped to 1–10.

### 4.4 Storage — `src/integrations/image_storage.py`

```python
AzuriteImageStorage().upload_image(image_bytes: bytes, blob_name: str) -> str     # blob URL
LocalImageStorage().upload_image(image_bytes, blob_name) -> str                   # local file path
ImageStorageManager().upload_image(image_bytes, blob_name) -> dict
# {"storage_provider": "azurite" | "local", "image_path", "image_url"}; falls back to local disk
```

### 4.5 Quality and guardrails

```python
from src.utils.quality_validation import evaluate_content_quality
evaluate_content_quality(content: str, content_type: str, keywords: list[str] | None = None,
                         blog_data: dict | None = None) -> dict
# {"score": int 0-100, "grade": "Excellent"|"Good"|"Needs Improvement"|"Poor",
#  "checks": {check: {...}}, "suggestions": [str]}

from src.guardrails.prompt_injection_guard import check_prompt_injection
check_prompt_injection(text: str) -> InjectionCheckResult      # .is_suspicious, .matched_patterns

from src.guardrails.research_guardrails import validate_research_output          # dict -> dict (raises)
from src.guardrails.grounding_guardrails import validate_research_grounding      # (research_data, search_results) -> dict
from src.guardrails.content_output_guardrails import validate_linkedin_output, validate_blog_output, validate_content_text
from src.guardrails.input_guardrails import UserRequestInput, QueryAnalysisOutput  # Pydantic models
```

---

## 5. Repositories (MongoDB)

All functions scope by `user_id`, return plain dicts without `_id`, and raise `ValueError` on invalid input.
Collections and indexes are documented in the [Deployment Guide](deployment-guide.md#1-mongodb-data-model).

### 5.1 `conversation_repository`

```python
create_conversation(user_id, content_type, title, topic="", target_audience="", tone="Professional",
                    metadata=None) -> dict          # conversation_id = thread_id = "conv_<hex>", status "active"
get_conversation(conversation_id, user_id) -> dict | None
list_conversations(user_id, limit=20, status=None) -> list[dict]       # 1 ≤ limit ≤ 100, newest updated first
update_conversation(conversation_id, user_id, *, title=None, status=None, topic=None,
                    target_audience=None, tone=None, metadata_updates=None) -> bool   # metadata merged per key
delete_conversation(conversation_id, user_id) -> bool                  # does not delete messages
ensure_indexes() -> None
```

`content_type`: `research`, `seo_blog`, `linkedin`, `image`, `strategy`, `multi`, `chat`.
`status`: `active`, `awaiting_approval`, `completed`, `failed`, `archived`.

### 5.2 `message_repository`

```python
add_message(conversation_id, user_id, role, message_type, content_type, content,
            agent_name=None, metadata=None) -> dict      # atomic per-conversation sequence number
get_message(message_id, user_id) -> dict | None
list_messages(conversation_id, user_id, limit=100, before_sequence=None) -> list[dict]   # chronological
list_user_messages_by_type(user_id, message_type, limit=100) -> list[dict]               # newest first
count_messages(conversation_id, user_id) -> int
update_message(message_id, conversation_id, user_id, *, content=None, status=None,
               metadata_updates=None) -> bool
ensure_indexes() -> None
```

`role`: `user`, `assistant`, `system`, `tool`. Message types used by the app:

| `message_type` | Written by | `content` |
|---|---|---|
| `request` | `create_content_conversation` | The user's request |
| `question` | `record_pause` | The agent's question (`metadata.options`, `metadata.lookup_key`) |
| `answer` | `answer_question`, `record_multi_answer` | The user's answer text |
| `generated_content` | research, strategist, generators | Structured draft (dict); `metadata.status`, `metadata.content_text`, quality fields |
| `generated_image` | image generator | Image path; `metadata` holds prompt, preferences, status, count |
| `review` | `submit_decision`, `submit_image_decision`, `record_multi_review` | Review label; `metadata.review_action` |
| `final_content` | approvals, `finalize_multi` | Approved text or image path |
| `error` | `record_failure` | Failure message |
| `chat` | `save_chat_turn` | Chat turns |

### 5.3 `profile_repository` (collection `user_profiles`)

```python
upsert_profile(user_id, conversation_id, profile_markdown) -> dict
get_profile(user_id, conversation_id) -> dict | None
delete_profile(user_id, conversation_id) -> bool
ensure_indexes() -> None   # unique (user_id, conversation_id); drops the legacy uq_profile_user_id index
```

### 5.4 `user_repository`

```python
create_user(user_id, username, auth_provider="local", auth_subject=None) -> dict   # upsert on (auth_provider, auth_subject)
get_user_by_id(user_id) -> dict | None
update_username(user_id, username) -> bool
```

### 5.5 Connection — `src/integrations/mongodb_client.py`

```python
get_mongo_client() -> MongoClient       # cached; MONGODB_URI; serverSelectionTimeoutMS=5000
get_database() -> Database              # MONGODB_DATABASE (default contentalchemy_db)
check_mongodb_connection() -> bool      # admin ping
```

---

## 6. Errors surfaced to the UI

| Error | Origin | Typical cause |
|---|---|---|
| `pydantic.ValidationError` | input guardrails | Request shorter than 3 / longer than 5,000 characters, or an invalid LLM analysis |
| `ValueError("Query Handler returned invalid JSON.")` | query handler | Non-JSON model output |
| `RuntimeError("No search results found for the given topic.")` | research agent | Both search providers failed or returned nothing |
| `ValueError("… cites a URL not present in the original search results …")` | grounding guardrail | Fabricated source |
| `ValueError("Content strategist output is missing the content strategy separator.")` | strategist | Model ignored the output format |
| `ValueError("Generated content contains unsafe markup: …")` | output guardrail | Script, iframe or event-handler markup |
| `TextProviderManagerError` | text manager | Every provider failed (lists each reason) |
| `image_status="failed"` + `image_error` | image generator | Every image provider failed (credits or other errors) |
