# SIGNAL

### AI. Without the noise.

SIGNAL is an AI-focused news aggregator built to make it easier to follow the rapidly changing world of artificial intelligence.

It brings together news and updates from leading AI companies alongside discoveries from across the wider AI ecosystem, presenting everything in a clean, chronological interface.

---

## What is SIGNAL?

AI news is everywhere.

New models, research papers, product launches, funding announcements, partnerships, releases, and breakthroughs appear every day across hundreds of sources.

SIGNAL brings that information into one place.

The platform is organized around three primary views:

### Home

Home brings everything together.

Company updates and discovery articles are combined into a single chronological feed, with the latest developments appearing first.

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

Discovery surfaces articles and discussions from external publishers and communities, allowing users to discover developments that may not originate directly from an AI company.

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
- **AI summaries — read the story without leaving**
- **Light and dark mode**
- **Responsive — built for phones as well as desktop**
- **Persistent article archive**
- **Feedback and source suggestions**
- **Clean, minimal interface**

---

## Tech Stack

### Frontend

- HTML
- CSS
- JavaScript

### Backend

- Python
- Flask

### Database

- Supabase
- PostgreSQL

### Data

- RSS feeds
- Web sources
- Custom filtering and classification
- Duplicate detection

### AI

- Google Gemini (free tier)

---

## AI Summaries

SIGNAL provides an AI-generated summary for every article, giving you the key information before you read the full story.

Each summary is **150–250 words** and focuses on the names, numbers, events, and specifics that matter to the story. The original article is linked at the end for readers who want to explore further.

Summaries are generated during article ingestion and stored alongside the article. This means they are ready instantly when an article is opened, while each story only needs to be summarized once.

### How a Summary Is Built

```text
article URL ──▶ extract.py ──▶ summarize.py ──▶ stored
                (extract content)  (Gemini)
```

SIGNAL retrieves the article's content directly from its source before sending it to the summarization model. The extracted content is then processed by Gemini and the resulting summary is stored in the database.

When the full article cannot be extracted, SIGNAL falls back to the information provided by the source feed.

### When a Summary Isn't Available

Some articles cannot be reliably extracted because of:

- Paywalls
- Consent screens
- Browser-rendered content
- Other access restrictions

In these cases, the article remains available with its original description instead of an AI-generated summary.

A summarization failure never prevents an article from appearing on SIGNAL.

The site also functions normally without a `GEMINI_API_KEY`; articles simply display their original descriptions when a summary is unavailable.
---

## Project Structure

```text
SIGNAL/
│
├── backend/
│   ├── data/
│   │
│   ├── classify.py
│   ├── db.py
│   ├── dedupe.py
│   ├── extract.py
│   ├── filters.py
│   ├── homepage.py
│   ├── ingest.py
│   ├── main.py
│   ├── migrate_submissions.py
│   ├── news.py
│   ├── refresh.py
│   ├── schema.sql
│   ├── scrape.py
│   ├── search.py
│   ├── sources.py
│   ├── submissions.py
│   ├── summarize.py
│   │
│   ├── .env.example
│   └── requirements.txt
│
├── frontend/
│   ├── logos/
│   ├── app.js
│   ├── index.html
│   └── style.css
│
├── .gitignore
├── dev.py
└── README.md
```

---

## Running Locally

### 1. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Supabase

Create the database using `backend/schema.sql` in the Supabase SQL Editor.

Then create your environment file:

```bash
cp .env.example .env
```

Add your Supabase credentials to `.env`, plus a free [Google AI Studio](https://aistudio.google.com/apikey) key as `GEMINI_API_KEY` for summaries.

The `.env` file contains private credentials and must never be committed to Git.

### 3. Start SIGNAL

From the project root:

```bash
python dev.py
```

Open the local address shown in the terminal.

`dev.py` starts the backend and the frontend together, and Ctrl+C stops both.

### 4. Keep the feed fresh

```bash
python refresh.py
```

This ingests from every source and summarises whatever is new.

Put it on a schedule to keep SIGNAL current:

```text
*/10 * * * *  cd /path/to/backend && python refresh.py
```

Summaries can also be written on their own:

```bash
python summarize.py              # everything outstanding
python summarize.py 20           # at most twenty
python summarize.py --retry-thin # try unreadable pages again
```

---

## License

This project is currently for personal development and experimentation.