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
- **Persistent article archive**
- **Clean, minimal interface**

---

## Architecture

SIGNAL is split into two primary layers:

```text
SIGNAL/
│
├── backend/
│   ├── data/
│   │
│   ├── classify.py
│   ├── db.py
│   ├── dedupe.py
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
│   │
│   ├── .env.example
│   └── requirements.txt
│
├── frontend/
│   ├── logos/
│   │
│   ├── app.js
│   ├── index.html
│   └── style.css
│
├── .gitignore
├── dev.py
└── README.md
```

---

## Database

SIGNAL stores its articles in Postgres, on Supabase.

Ingestion and serving are separate jobs. Ingestion goes out to the sources, filters what it finds, and writes it to the store. A page load only ever reads the store back.

```text
sources ──▶ ingest ──▶ Postgres ──▶ API ──▶ frontend
            (on a schedule)        (per request)
```

That separation is what makes the archive an archive. Before it, everything lived in memory for ten minutes at a time: a restart lost the lot, and any story a feed stopped carrying disappeared from the site with it. Now a source going quiet, going slow, or going down costs nothing at read time.

### Tables

| Table | Holds |
| --- | --- |
| `articles` | Every article ever ingested, identified by its canonical URL |
| `ingest_runs` | What each run saw, and which sources failed |
| `submissions` | Feedback and source suggestions from the footer forms |

### One story, one row

Duplicates were already dropped inside a single ingest. The store extends that across runs: a new article is checked against everything already held, using the same rules.

It also lets a stored story be replaced. A newsroom writing up a launch is often stored hours before the company's own post arrives, and turning that post away as a duplicate would keep it off the company's own page. So when a better source turns up with the same story, it takes the place of the one already there:

```text
company  ▶  publisher  ▶  aggregator
```

---

## Running locally

### 1. Install

```bash
cd backend
pip install -r requirements.txt
```

### 2. Create the tables

In the Supabase dashboard for the SIGNAL project, open the SQL Editor and run `backend/schema.sql`. It is safe to re-run.

### 3. Point the backend at the project

```bash
cp .env.example .env
```

Fill in `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from **Settings → API**.

The service role key bypasses row level security, so it belongs on the server only. `.env` is gitignored, and the key must never reach the frontend or a commit.

### 4. Fill the store

```bash
python refresh.py
```

This is the only part that talks to the feeds, which makes it the thing to put on a schedule:

```text
*/10 * * * *  cd /path/to/backend && python refresh.py
```

### 5. Run it

From the project root:

```bash
python dev.py
```

That starts both halves and streams their output into one terminal, each line labelled with the server it came from:

```text
[dev]      backend on http://127.0.0.1:5050
[dev]      frontend on http://127.0.0.1:5500
[dev]      open http://127.0.0.1:5500
[dev]      Ctrl+C stops both
```

Open **http://127.0.0.1:5500**. Ctrl+C stops both servers.

`dev.py` only starts things. The two halves stay exactly as they are — the API on 5050, the site on 5500, talking over CORS — and it changes nothing about how either behaves. It checks both ports first, because half a stack coming up is more confusing than none of it, and if one server exits on its own it stops the other rather than leaving a half-running app.

To start them by hand instead, in two terminals:

```bash
cd backend   && python main.py                    # the API
cd frontend  && python3 -m http.server 5500       # the site
```

`GET /api/health` reports whether the store is reachable and what the last ingest did, without triggering one.

### Moving the old submissions across

Submissions used to be appended to `data/submissions.jsonl`. To move anything that collected there into the table:

```bash
python migrate_submissions.py
```

It can be run twice without duplicating anything, and it leaves the file where it is.

### Without a database

If `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are unset, or the store cannot be reached, the site does not go dark. It falls back to what it did before: ingesting into memory and serving that. Everything works except the part the store exists for, which is remembering anything beyond what the feeds are carrying right now.
