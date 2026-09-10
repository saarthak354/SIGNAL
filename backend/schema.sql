-- ===================================
-- SIGNAL — DATABASE SCHEMA
-- ===================================
--
-- Run once against the SIGNAL project:
--   Supabase dashboard -> SQL Editor -> paste -> Run
--
-- Safe to re-run: every statement is guarded.


-- -----------------------------------
-- ARTICLES
-- -----------------------------------
--
-- The store the whole site reads from.
--
-- Ingestion used to hold everything in memory
-- for ten minutes at a time, so a restart lost
-- the lot and any story a feed stopped carrying
-- was gone with it. These rows are the archive
-- that replaces that: a feed dropping a story
-- no longer takes it off the site.

create table if not exists public.articles (

    id                  bigint generated always as identity primary key,

    -- Where the article lives, and the same
    -- link reduced to what identifies it:
    -- no scheme, no www, no tracking tail.
    -- That reduced form is the identity, so
    -- one story can only ever hold one row.
    url                 text        not null,
    url_key             text        not null unique,

    title               text        not null,
    description         text        not null default '',

    -- Who published it, which feed carried it,
    -- and what kind of source that makes it.
    -- The homepage ranking weighs the tier.
    source              text        not null default '',
    via                 text        not null default '',
    source_tier         text        not null default 'aggregator'
                                    check (source_tier in ('company', 'publisher', 'aggregator')),

    -- Which tab it belongs to. A company writing
    -- on its own site is "company"; everything
    -- else is "discovery".
    category            text        not null
                                    check (category in ('company', 'discovery')),

    -- Set when the company published it itself.
    company             text,
    company_id          text,

    -- Set instead when somebody else wrote about
    -- that company. Kept apart from the columns
    -- above on purpose: one article must never
    -- show up under both tabs.
    related_company     text,
    related_company_id  text,

    published           timestamptz not null,
    updated             timestamptz,

    -- When we first saw it, and the last time it
    -- was still being carried by a live feed.
    first_seen_at       timestamptz not null default now(),
    last_seen_at        timestamptz not null default now()
);


-- The feed is always "newest first, within a
-- window", so every read starts from this.
create index if not exists articles_published_idx
    on public.articles (published desc);

-- The Companies and Discovery tabs.
create index if not exists articles_category_published_idx
    on public.articles (category, published desc);

-- One company's own page. Partial, because most
-- rows have no company_id and there is no query
-- that wants those in this index.
create index if not exists articles_company_published_idx
    on public.articles (company_id, published desc)
    where company_id is not null;


-- -----------------------------------
-- INGEST RUNS
-- -----------------------------------
--
-- Reads no longer trigger a fetch, so "how many
-- entries did the sources hand us" and "which
-- source failed" are no longer facts the request
-- itself knows. They are recorded here instead,
-- and the API reports the latest row.

create table if not exists public.ingest_runs (

    id            bigint generated always as identity primary key,

    started_at    timestamptz not null default now(),
    finished_at   timestamptz,

    -- Raw entries the sources returned, before
    -- any filtering.
    ingested      integer     not null default 0,

    -- What survived the date, relevance and
    -- duplicate filters.
    kept          integer     not null default 0,

    -- What that meant for the store.
    inserted      integer     not null default 0,
    refreshed     integer     not null default 0,
    replaced      integer     not null default 0,

    -- [{"source": "...", "error": "..."}]
    errors        jsonb       not null default '[]'::jsonb
);


create index if not exists ingest_runs_started_idx
    on public.ingest_runs (started_at desc);


-- -----------------------------------
-- SUBMISSIONS
-- -----------------------------------
--
-- Feedback and source suggestions from the
-- footer forms. These lived in an append-only
-- JSONL file until this table existed.

create table if not exists public.submissions (

    id            bigint generated always as identity primary key,

    type          text        not null
                              check (type in ('feedback', 'source')),

    name          text        not null,
    message       text        not null,

    submitted_at  timestamptz not null default now()
);


create index if not exists submissions_submitted_idx
    on public.submissions (submitted_at desc);


-- -----------------------------------
-- ROW LEVEL SECURITY
-- -----------------------------------
--
-- The backend holds the service role key, which
-- bypasses all of this. These policies decide
-- what the anon key could do if the frontend
-- ever talked to Supabase directly.
--
--   articles       readable by anyone, the site is public
--   ingest_runs    closed, it is operational detail
--   submissions    closed, people wrote these to us
--
-- Enabling RLS with no policy denies everything,
-- so the last two need no policy of their own.

alter table public.articles    enable row level security;
alter table public.ingest_runs enable row level security;
alter table public.submissions enable row level security;


drop policy if exists "articles are public" on public.articles;

create policy "articles are public"
    on public.articles
    for select
    to anon, authenticated
    using (true);


-- -----------------------------------
-- SUMMARIES
-- -----------------------------------
--
-- Added after the fact, so these are ALTERs
-- rather than part of the table above. Re-running
-- the whole file stays safe.
--
-- The summary is written once, when an article
-- first arrives, and read on every open. Doing it
-- the other way round -- writing it when somebody
-- clicks -- would mean the first reader of every
-- article waits for a model, and the same article
-- gets summarised again on every machine that has
-- not cached it. Dedupe already guarantees one row
-- per story, so this way each story costs exactly
-- one summary, ever.
--
--   status  pending   never attempted
--           ok        summary is there
--           thin      no readable article at that URL
--                     (paywall, consent wall, JS-only page)
--           failed    the model or the fetch errored; retried

alter table public.articles
    add column if not exists summary        text;

alter table public.articles
    add column if not exists summary_status text not null default 'pending';

alter table public.articles
    add column if not exists summary_model  text;

alter table public.articles
    add column if not exists summary_error  text;

alter table public.articles
    add column if not exists summarized_at  timestamptz;

alter table public.articles
    add column if not exists summary_attempts integer not null default 0;


-- The summariser's own query: what still needs
-- one, newest first. Partial, because the rows
-- it wants are the minority and shrinking.
create index if not exists articles_summary_pending_idx
    on public.articles (published desc)
    where summary_status in ('pending', 'failed');
