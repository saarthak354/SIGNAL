# -----------------------------------
# SOURCE REGISTRY
# -----------------------------------
#
# Every source declares:
#
#   id        stable key used by the frontend
#   name      label shown on the article card
#   method    "rss" or "scrape"
#   category  "company" or "discovery"
#   trusted   True  = everything it posts is AI news
#             False = it also posts non AI content,
#                     so the keyword filter applies


# -----------------------------------
# COMPANIES
# -----------------------------------

COMPANY_SOURCES = [

    {
        "id": "openai",
        "domains": ["openai.com"],
        "aliases": ["openai", "chatgpt", "gpt", "sora", "dall-e", "dalle", "codex", "sam altman"],
        "name": "OpenAI",
        "method": "rss",
        "trusted": True,
        "url": "https://openai.com/news/rss.xml",
    },

    {
        "id": "anthropic",
        "domains": ["anthropic.com", "claude.ai"],
        "aliases": ["anthropic", "claude"],
        "name": "Anthropic",
        "method": "scrape",
        "trusted": True,

        "url": "https://www.anthropic.com/news",
        "base_url": "https://www.anthropic.com",
        "path_filter": "/news/",

        # Anthropic ships hashed CSS class names,
        # so try stable tags before class matches.
        "title_selector": ["h2", "h3", "h4", "[class*='title']"],
        "description_selector": ["p"],
        "date_selector": ["time", "[class*='date']"],
    },

    {
        "id": "google-deepmind",
        "domains": ["deepmind.google", "deepmind.com", "ai.google"],
        "aliases": ["deepmind", "gemini", "alphafold", "alphagenome", "alphago", "weathernext", "imagen", "google ai", "google's ai"],
        "name": "Google DeepMind",
        "method": "rss",
        "trusted": True,
        "url": "https://deepmind.google/blog/rss.xml",
    },

    {
        "id": "meta-ai",
        "domains": ["ai.meta.com", "engineering.fb.com"],
        "aliases": ["meta ai", "meta's ai", "llama", "meta platforms", "facebook ai", "pytorch"],
        "name": "Meta AI",
        "method": "scrape",

        # The engineering blog also covers
        # non-AI infrastructure work.
        "trusted": False,

        # ai.meta.com returns HTTP 400 to anything
        # that is not a real browser, so Meta's
        # engineering blog is the usable source.
        "url": "https://engineering.fb.com/category/ai-research/",
        "base_url": "https://engineering.fb.com",
        "path_filter": "engineering.fb.com/20",

        "container_selector": ["article"],
        "title_selector": ["h1", "h2", "h3", "[class*='entry-title']"],
        "description_selector": ["[class*='excerpt']", "p"],
        "date_selector": ["time", "[datetime]", "[class*='date']"],

        # WordPress puts the date in the URL:
        # /2026/09/02/ml-applications/slug/
        "date_url_pattern": r"/(\d{4})/(\d{2})/(\d{2})/",
    },

    {
        "id": "deepseek",
        "domains": ["deepseek.com"],
        "aliases": ["deepseek"],
        "name": "DeepSeek",
        "method": "scrape",
        "trusted": True,

        # The news index only renders in full on an
        # article page, so hop to the first article
        # and read the sidebar there.
        "url": "https://api-docs.deepseek.com/news/",
        "base_url": "https://api-docs.deepseek.com",
        "path_filter": "/news/news",
        "follow_link": True,

        "title_selector": ["self"],
        "description_selector": [],
        "date_selector": [],

        # Slugs encode the date: news260821 -> 2026-08-21
        "date_url_pattern": r"/news/news(\d{2})(\d{2})(\d{2})$",
        "date_url_century": "20",

        # Skip the language switcher and the
        # translated copies of every page
        "exclude_url_patterns": ["/zh-cn/"],
        "min_title_length": 15,
    },

    {
        "id": "nvidia",
        "domains": ["nvidia.com"],
        "aliases": ["nvidia", "cuda", "blackwell", "h100", "gb200", "tensor core"],
        "name": "NVIDIA",
        "method": "rss",

        # NVIDIA's blog also covers gaming and
        # graphics, so require an AI signal.
        "trusted": False,
        "url": "https://blogs.nvidia.com/feed/",
    },

    {
        "id": "microsoft-ai",
        "domains": ["microsoft.com"],
        "aliases": ["microsoft", "copilot", "azure ai", "bing ai"],
        "name": "Microsoft AI",
        "method": "rss",
        "trusted": False,

        # The AI newsroom page ships no dates in its
        # markup, so the matching topic feed is the
        # only way to get publish dates.
        "url": "https://news.microsoft.com/source/topics/ai/feed/",
    },

    {
        "id": "xai",
        "domains": ["x.ai"],
        "aliases": ["xai", "x.ai", "grok"],
        "name": "xAI",
        "method": "scrape",
        "trusted": True,

        "url": "https://x.ai/news",
        "base_url": "https://x.ai",
        "path_filter": "/news/",

        "title_selector": ["h1", "h2", "h3", "[class*='title']", "self"],
        "description_selector": ["p"],
        "date_selector": ["time", "[class*='date']"],
    },
]


# -----------------------------------
# DISCOVERY
# -----------------------------------
#
# Everyone who is not the company itself.

DISCOVERY_SOURCES = [

    {
        "id": "hacker-news",
        "name": "Hacker News",
        "method": "rss",
        "trusted": False,
        "url": "https://news.ycombinator.com/rss",
    },
]


# -----------------------------------
# HELPERS
# -----------------------------------

def all_sources():

    sources = []

    for source in COMPANY_SOURCES:

        sources.append({
            **source,
            "category": "company"
        })

    for source in DISCOVERY_SOURCES:

        sources.append({
            **source,
            "category": "discovery"
        })

    return sources


def companies():

    return [
        {
            "id": source["id"],
            "name": source["name"]
        }
        for source in COMPANY_SOURCES
    ]
