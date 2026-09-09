# SIGNAL

### AI. Without the noise.

SIGNAL is an AI-focused news aggregator built to make it easier to follow the rapidly changing world of artificial intelligence.

It brings together news and updates from leading AI companies alongside discoveries from across the wider AI ecosystem, presenting everything in a clean, chronological interface.

---

## What is SIGNAL?

AI news is everywhere.

New models, research papers, product launches, funding announcements, partnerships, releases, and breakthroughs appear every day across hundreds of sources.

SIGNAL brings that information into one place.

The platform is organized around two primary sources of information:

### Companies

Follow news directly from the companies building AI.

SIGNAL organizes company-published articles by organization, making it easy to explore the latest updates from companies such as:

- OpenAI
- Anthropic
- Google DeepMind
- Meta AI
- Microsoft AI
- NVIDIA
- xAI
- DeepSeek
- and more

Each company has its own dedicated view containing its latest articles.

### Discovery

Explore AI news from the wider internet.

Discovery surfaces articles and discussions from external sources and communities, allowing users to discover developments that may not originate directly from an AI company.

---

## Home

The Home feed brings everything together.

Company updates and discovery articles are combined into a single chronological feed, with the latest developments appearing first.

The goal is simple:

**Open SIGNAL and see what is happening in AI right now.**

---

## Features

- **AI-focused news feed**
- **Chronological article aggregation**
- **Company-specific news feeds**
- **Discovery feed for external sources**
- **Company directory with logos and article counts**
- **Article source and publication timestamps**
- **Direct links to original articles**
- **Search functionality**
- **Duplicate article handling**
- **Article filtering and classification**
- **RSS and web-based ingestion**
- **Clean, minimal interface**

---

## Architecture

SIGNAL is split into two primary layers:

```text
SIGNAL
│
├── backend/
│   ├── classify.py
│   ├── dedupe.py
│   ├── filters.py
│   ├── ingest.py
│   ├── main.py
│   ├── news.py
│   ├── scrape.py
│   ├── search.py
│   ├── sources.py
│   └── submissions.py
│
├── frontend/
│   ├── logos/
│   ├── app.js
│   ├── index.html
│   └── style.css
│
├── .gitignore
└── README.md