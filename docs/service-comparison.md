# AI Service Comparison Analysis

How the external AI services wired into ContentAlchemy compare on cost, speed, reliability and output quality, and
which combination to configure for a given budget or quality target.

| | |
|---|---|
| **Covers** | Text LLMs (OpenAI, Anthropic Claude, Google Gemini, Perplexity), web search (SerpApi, Tavily), image generation (Stability AI, OpenAI, Gemini) |
| **Measured data** | `logs/contentalchemy.log`, 28 Oct – 13 Nov 2026 |
| **Prices** | Public list prices gathered in November 2026 from provider pages and pricing trackers (see [Sources](#sources)). Prices change often, so verify them before budgeting |

> **How to read this document.** Latency and reliability numbers are measured from this project's own logs, using
> the models configured in `.env`. Cost per workflow is **estimated** from the token budgets in the code and the list
> prices below. Quality notes are qualitative, based on how each provider behaved against this project's prompts and
> validators.

---

## 1. How the services are used

| Capability | Code path | Default order | Configured by |
|---|---|---|---|
| Text generation (all agents) | `TextProviderManager` | OpenAI → Claude → Gemini → Perplexity | `TEXT_PRIMARY_PROVIDER`, `TEXT_FALLBACK_PROVIDERS` |
| Image prompt + preference extraction, general chat | `openai_client` directly | OpenAI only | `OPENAI_MODEL` |
| Web search (research agent) | `serp_client.search_web` | SerpApi (Google) → Tavily | `SERPAPI_KEY`, `TAVILY_API_KEY` |
| Image generation | `ImageProviderManager` | Stability → OpenAI → Gemini | `IMAGE_PRIMARY_PROVIDER`, `IMAGE_FALLBACK_PROVIDERS`, `*_IMAGE_ENABLED` |

### Token budget per LLM call (from the code)

| Call | `max_output_tokens` | Typical input | Output format |
|---|---|---|---|
| Query handler | 700 | ~0.6k | Strict JSON |
| Research synthesis | 3,000 | ~2.5k (system prompt + 5 search results) | Strict JSON |
| Content strategist | 7,000 | ~3.5k | Markdown with separator |
| SEO blog (streamed) | 4,000 | ~5k (report + strategy) | Strict JSON with long `blog_article` |
| LinkedIn writer | 1,600 | ~4.5k | Strict JSON |
| Image preference extraction | 200 | ~0.4k | Strict JSON |
| Image prompt enhancement | 500 | ~0.5k | Plain text |

Most calls need **strict JSON**, and output is checked by Pydantic and grounding validators. JSON reliability
therefore matters more than raw writing quality for every step except the strategist and the blog article body.

---

## 2. Text LLMs: OpenAI vs alternatives

### 2.1 List prices (USD per 1M tokens, November 2026)

| Provider · model (as configured) | Input | Output | Notes |
|---|---|---|---|
| OpenAI · `gpt-4o-mini` | $0.15 | $0.60 | Cheapest configured option; Batch API and cached input cost less |
| Google · `gemini-2.5-flash` | $0.30 | $2.50 | Free tier available with rate limits |
| Anthropic · Claude Haiku 4.5 | $1.00 | $5.00 | Option for a cheaper Claude fallback (set `CLAUDE_DEFAULT_MODEL`) |
| Anthropic · `claude-sonnet-5-5` (default) | $2.00 | $10.00 | Trackers disagree; earlier Sonnet generations were $3 / $15 |
| Perplexity · `sonar` | $1.00 | $1.00 | **Plus** a request fee of $5–12 per 1,000 requests, depending on search-context size |

### 2.2 Estimated LLM cost per workflow

Approximate token totals for a run, from the budgets above (input / output): research ≈ 3.1k / 1.7k · research +
strategy ≈ 6.6k / 5.2k · **SEO blog ≈ 12k / 8k** · LinkedIn ≈ 11k / 5.8k · image ≈ 1.7k / 0.5k (text only).

| Workflow | gpt-4o-mini | gemini-2.5-flash | Claude Haiku 4.5 | Claude Sonnet 5.5 | Perplexity Sonar* |
|---|---|---|---|---|---|
| Research report | $0.0015 | $0.005 | $0.012 | $0.023 | $0.015 |
| SEO blog | **$0.007** | $0.024 | $0.052 | $0.104 | $0.040 |
| LinkedIn post | $0.005 | $0.018 | $0.040 | $0.080 | $0.037 |
| Multi (blog + LinkedIn + image) | $0.008 | $0.028 | $0.063 | $0.126 | $0.051 |

\* Includes the $0.005 low-context request fee per call. Perplexity runs its own web search on every call, which this
pipeline doesn't need, so most of that fee buys nothing here.

**Takeaway:** `gpt-4o-mini` is about **3× cheaper than Gemini Flash and about 15× cheaper than Claude Sonnet** for the
same pipeline. At these prices, LLM tokens are not the main cost of a request; search and images are (§5).

### 2.3 Measured performance (OpenAI `gpt-4o-mini` primary)

Node durations from the logs, excluding mocked test runs (< 0.5 s):

| Node | Runs | Median | p90 | Max |
|---|---|---|---|---|
| Query handler | 42 | 2.9 s | 3.9 s | 5.4 s |
| Research agent (search + synthesis) | 25 | 14.3 s | 19.4 s | 56.7 s |
| ↳ LLM synthesis only | 24 | avg 14.8 s | — | 55.3 s |
| Content strategist | 24 | 20.9 s | 31.4 s | 38.1 s |
| Content generator (single) | 18 | 6.5 s | 18.9 s | 26.1 s |
| Multi content generator | 8 | 9.8 s | 21.0 s | 27.6 s |
| Image request analyzer | 14 | 1.5 s | 1.8 s | 2.1 s |

Claude, Gemini and Perplexity served traffic only as fallbacks, so there is not enough data to benchmark their
latency in this project. To compare them, set each one as `TEXT_PRIMARY_PROVIDER` for a few runs and compare the
`Node finished` lines.

### 2.4 Observed reliability

Provider outcomes logged by `TextProviderManager`. The period includes **deliberate failure testing** (an invalid
OpenAI key, quota-limited accounts), so treat failures as evidence that fallback works, not as vendor uptime figures.

| Provider | Successful calls | Logged failures | Failure types |
|---|---|---|---|
| OpenAI | 233 generate + 17 stream | 28 | 27 × access error (invalid-key test), 1 × other |
| Gemini | 21 | 12 | 11 × access error, 1 × other |
| Claude | 0 | 27 | 26 × quota error (account without credit) |
| Perplexity | 0 | 1 | 1 × other |

When OpenAI was disabled, requests completed on **Gemini** after Claude failed on quota, which is the fallback chain
working as designed.

### 2.5 Qualitative comparison

| Criterion | OpenAI gpt-4o-mini | Gemini 2.5 Flash | Claude Sonnet 5.5 | Perplexity Sonar |
|---|---|---|---|---|
| Strict-JSON reliability | High | High | High | Lower: answers are search-grounded prose with citations; more parse failures expected |
| Long-form writing (strategy, blog) | Good, sometimes generic | Good | **Best** for nuance, structure and tone control | Adequate |
| Speed | Fast | Fast | Moderate | Fast, plus search time |
| Built-in web grounding | No | Optional (not used) | No | **Yes**, but redundant with SerpApi/Tavily here |
| Cost | **Lowest** | Low | High | Medium (request fee) |
| Best role here | Primary | Primary for budget or as first fallback | Primary for premium quality, or fallback | Last-resort fallback |

---

## 3. Web search: SerpApi vs Tavily

| | SerpApi (Google) | Tavily |
|---|---|---|
| Role in the code | Primary (`search_google`) | Fallback (`search_tavily`) when SerpApi errors or returns no valid URLs |
| What you get | Google organic results: title, link, snippet | LLM-oriented results: title, URL, extracted `content` (used as the snippet) |
| Pricing | Free 250 searches/month; paid from about $25 / 1,000 searches (≈ $0.025 each), falling to ≈ $0.009 each at 30k/month | 1,000 free credits/month; then about $0.008 per basic search |
| Call settings | `engine="google"`, `num=5`, `no_cache=True` | `search_depth="basic"`, `max_results=5` |
| Strengths | Exactly what ranks on Google, which matters for SEO; mature, many engines | Cheaper; richer snippets give the synthesis model more facts per result |
| Weaknesses | Several times the cost; `no_cache=True` disables SerpApi's free cache so every search is billed; snippets are short | Not a Google SERP, so less useful for "what ranks for this keyword" |
| Observed | Average search time 2.8 s (max 9.1 s) for the research step | Served 11 requests when Google returned no valid results |

**Cost-benefit.** Search costs more than all the LLM calls combined. A research request with SerpApi at starter
pricing is ≈ $0.025 for search against ≈ $0.0015 for `gpt-4o-mini` tokens.

- For **research and LinkedIn**, where you need facts rather than rankings, Tavily-first cuts the search cost by about 3×
  and gives the model fuller excerpts.
- For **SEO blogs**, where competitor rankings matter, keep SerpApi first.
- Removing `no_cache=True` lets repeated queries hit SerpApi's cache at no charge.

The order is hard-coded in `search_web`. Making it configurable (like the text and image managers) is a small,
low-risk change.

---

## 4. Image generation: Stability vs OpenAI vs Gemini

| | Stability AI · Stable Image Core | OpenAI · `gpt-image-*` | Google · `gemini-3.1-flash-image` |
|---|---|---|---|
| Role in the code | Primary (`stability_provider.py`) | Fallback (`openai_provider.py`) | Fallback (`gemini_provider.py`) |
| Price | 3 credits ≈ **$0.03 / image**; 25 free credits at sign-up | Billed by image tokens; depends on model, size and quality (check OpenAI's pricing page) | ≈ $0.045–$0.151 / image by resolution (≈ $0.067 at 1K); needs a billing-enabled key |
| Sizes in code | 1:1, 9:16, 16:9 (all three orientations) | 1024², 1024×1536, 1536×1024; `1792×1024` (landscape) is not mapped and falls back to square | 1:1, 9:16, 16:9 aspect ratios |
| Strengths | Cheapest; good photographic and illustrative styles; simple REST API | Strong prompt adherence and **text rendering** inside images | Good composition and context; one key for text and images |
| Weaknesses | Weaker at rendering text in images; credit-based billing | Model access varies by account (logged: `model 'gpt-image-1' does not exist`, `Invalid size '1024x1792'`) | Free-tier keys rejected for image models |
| Measured | `image_generator` node median 5.8 s (p90 6.5 s), mostly Stability; 22 successful generations | 3 successful generations | 0 successes (quota/billing errors) |

**Observed failures** (from `ImageProviderManager` warnings):

| Provider | Count | Reason |
|---|---|---|
| Stability | 49 | Insufficient credits (HTTP 402) |
| Stability | 11 | Generic failure (*"Image generation failed."*) |
| Stability | 2 | Server error (HTTP 500) |
| OpenAI | 11 | Model not available to the account |
| OpenAI | 2 | Unsupported size (`1024x1792`) |
| Gemini | 3 | Quota / billing |

Credits, not technical faults, caused most image failures. That is why the manager raises a dedicated
`InsufficientCreditsError` when every provider fails on credits: the user then sees *"insufficient credits"* instead of a
generic error.

---

## 5. Cost-benefit analysis

### 5.1 Estimated cost per request, by stack

| Request | Budget stack¹ | Default stack² | Premium stack³ |
|---|---|---|---|
| Research report | $0.0095 | $0.027 | $0.048 |
| SEO blog | $0.015 | $0.032 | $0.129 |
| LinkedIn post | $0.013 | $0.030 | $0.105 |
| Image | $0.031 | $0.031 | ≈ $0.07–0.15 |
| Multi (blog + LinkedIn + image) | $0.046 | $0.063 | ≈ $0.22–0.30 |

¹ `gpt-4o-mini` + Tavily first + Stability Core. ² `gpt-4o-mini` + SerpApi starter + Stability Core (current
configuration). ³ Claude Sonnet 5.5 + SerpApi + OpenAI or Gemini images.

### 5.2 Monthly projection (100 SEO blogs, 100 LinkedIn posts, 50 images)

| Stack | LLM | Search | Images | **Total** |
|---|---|---|---|---|
| Budget | ≈ $1.20 | free (within Tavily's 1,000 free credits) | ≈ $1.50 | **≈ $2.70** |
| Default | ≈ $1.20 | free (SerpApi free tier) to $25 (starter plan) | ≈ $1.50 | **≈ $3–28** |
| Premium | ≈ $18.50 | $25 | ≈ $3.50–7.50 | **≈ $47–51** |

SerpApi's free 250 searches/month covers 200 research runs. Above that, the $25 plan is a fixed step cost.

### 5.3 Where the money goes (default stack, one SEO blog)

| Item | Cost | Share |
|---|---|---|
| SerpApi search | $0.025 | ~78% |
| LLM tokens (4 calls) | $0.007 | ~22% |

The cheapest improvement is therefore **not** a cheaper LLM. It is fewer or cheaper searches: Tavily first, the SerpApi
cache, or caching research per topic.

---

## 6. Recommendations

### Budget priority: lowest cost per piece

```env
TEXT_PRIMARY_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
TEXT_FALLBACK_PROVIDERS=gemini,claude
CLAUDE_DEFAULT_MODEL=claude-haiku-4-5        # cheap Claude as last resort

IMAGE_PRIMARY_PROVIDER=stability
IMAGE_FALLBACK_PROVIDERS=openai
STABILITY_IMAGE_ENABLED=true
OPENAI_IMAGE_ENABLED=true
GEMINI_IMAGE_ENABLED=false
```

Also make Tavily the primary search (code change in `search_web`) and drop `no_cache=True`. Expect ≈ $0.01–0.05 per
request.

### Balanced: current defaults, hardened

Keep `gpt-4o-mini` primary and Stability first, and order fallbacks **Gemini → Claude → Perplexity** (Gemini is cheaper
than Claude and, in the logs, recovered requests when OpenAI was unavailable). Keep SerpApi for SEO blogs. Remove
Perplexity if you want strict-JSON steps to fail fast rather than risk parse errors.

### Quality priority: best writing and images

```env
TEXT_PRIMARY_PROVIDER=claude
CLAUDE_DEFAULT_MODEL=claude-sonnet-5-5
TEXT_FALLBACK_PROVIDERS=openai,gemini

IMAGE_PRIMARY_PROVIDER=openai                 # best prompt adherence and in-image text
OPENAI_IMAGE_MODEL=<an image model enabled on your account>
IMAGE_FALLBACK_PROVIDERS=gemini,stability
```

A cheaper middle ground is a **per-step model split**: Claude for the content strategist and blog article (the
long-form steps where quality shows), `gpt-4o-mini` for classification, research JSON and image prompts. This needs a
small code change: pass `model=` or a provider per call. It keeps most of the quality gain for about a third of the
premium cost.

### Configuration hygiene, whatever the profile

- Only list fallback providers that have valid keys and credit. Failing providers add retry latency (up to 1 s + 2 s
  for retryable errors) before the next provider is tried.
- Check `OPENAI_IMAGE_MODEL` against your account: `gpt-image-1` was unavailable on the account used here.
- Gemini image generation needs a billing-enabled key.
- Monitor Stability credits: credit and quota errors caused 52 of the 81 logged image provider failures.

---

## Sources

Prices were gathered in November 2026. Several are from third-party trackers that disagree with each other; the
official pages are listed first in each group.

- OpenAI: [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing.md) · [G2 guide](https://www.g2.com/articles/openai-api-pricing) · [tokencalc](https://tokencalc.pages.dev/blog/openai-api-pricing-guide-2026)
- Anthropic: [docs.claude.com pricing](https://docs.claude.com/en/docs/about-claude/pricing) · [benchlm.ai](https://benchlm.ai/anthropic/api-pricing) · [finout.io](https://finout.io/blog/anthropic-api-pricing)
- Google Gemini: [ai.google.dev pricing](https://ai.google.dev/gemini-api/docs/pricing) · [puter.com breakdown](https://developer.puter.com/tutorials/gemini-api-pricing/) · [modelcompare.dev](https://modelcompare.dev/models/google/gemini-2-5-flash-image)
- Perplexity: [docs.perplexity.ai pricing](https://docs.perplexity.ai/docs/getting-started/pricing.md) · [amnic.com](https://amnic.com/blogs/perplexity-api-pricing)
- SerpApi and Tavily: [serpapi.com/pricing](https://serpapi.com/pricing.md) · [costbench SerpApi vs Tavily](https://www.costbench.com/compare/serpapi-vs-tavily/) · [apicostcalc](https://apicostcalc.com/blog/exa-vs-tavily-vs-serper-vs-brave-web-search-api-cost.html)
- Stability AI: [activepieces cost per image](https://www.activepieces.com/blog/stability-ai-api-pricing-in-2026-and-cost-per-image) · [mindstudio Stable Image Core](https://www.mindstudio.ai/blog/what-is-stable-image-core-stability-ai) · [costbench](https://costbench.com/software/ai-media-apis/stability-ai-api/)
