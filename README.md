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

Clicking an article opens it inside SIGNAL instead of sending you away.

Each article receives a 150-250 word summary containing the names, numbers, and specifics that carry the story, with a link to the original at the bottom.

Summaries are written when an article is ingested, not when it is clicked.

This keeps articles instant to open, and means each story is summarised once no matter how many people read it.

### How a summary is built

```text
article URL ──▶ extract.py ──▶ summarize.py ──▶ stored
                (read the page)  (Gemini)
```

Ingestion collects only a headline and a short blurb, so `extract.py` opens the article page itself.

Where a page refuses to open, the source RSS feed is used instead.

### When there is no summary

Some pages cannot be read at all.

- Paywalls
- Consent screens
- Articles rendered in the browser

These are marked `thin` and still open normally, showing the original blurb.

Nothing is ever dropped for failing to summarise.

Without `GEMINI_API_KEY` the site works normally, and articles open with their blurb.

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