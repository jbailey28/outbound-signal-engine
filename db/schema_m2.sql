-- outbound-signal-engine — Milestone 2 schema (affiliate/partner signals)
-- Target: Supabase / Postgres. Run after db/schema.sql.
--
-- Keeps the same raw/clean separation as M1:
--   raw_site_fetches  -> audit trail of every website fetch (Tier 2)
--   account_signals   -> the derived, usable signal per account

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- account_signals — one current affiliate/partner signal per account
-- ---------------------------------------------------------------------------
-- has_program: does this account run an affiliate/partner program?
--   true  = evidence found (named platform, program page, or network footprint)
--   false = checked and none found
--   null  = unknown / not yet checked
-- platform: normalized platform key ('impact', 'rakuten', 'cj', 'awin',
--   'shareasale', 'partnerstack', 'pepperjam', 'partnerize', 'refersion',
--   'tune', 'in_house', 'unknown')
-- source: how we learned it ('competitors_column' | 'website_scrape')
create table if not exists account_signals (
    id            uuid primary key default gen_random_uuid(),
    account_id    uuid not null references accounts(id) on delete cascade,
    signal_type   text not null default 'affiliate_program',

    has_program   boolean,             -- true / false / null(unknown)
    platform      text not null default 'unknown',
    source        text not null check (source in ('competitors_column', 'website_scrape')),
    confidence    text not null default 'low'
                  check (confidence in ('low', 'medium', 'high')),

    -- what we matched on: program_url, matched_pattern, network_domain, etc.
    evidence      jsonb not null default '{}'::jsonb,

    detected_at   timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- one current signal per account per signal_type (upsert target)
create unique index if not exists uq_account_signals_account_type
    on account_signals(account_id, signal_type);

create index if not exists idx_account_signals_platform on account_signals(platform);
create index if not exists idx_account_signals_has_program on account_signals(has_program);

comment on table account_signals is
    'Current affiliate/partner-program signal per account. Upserted per run.';

-- ---------------------------------------------------------------------------
-- raw_site_fetches — audit trail for Tier-2 website scraping
-- ---------------------------------------------------------------------------
create table if not exists raw_site_fetches (
    id            uuid primary key default gen_random_uuid(),
    account_id    uuid references accounts(id) on delete cascade,
    url           text not null,
    fetched_at    timestamptz not null default now(),
    http_status   integer,
    -- pages/paths probed and what matched, for full auditability
    probed_paths  jsonb not null default '[]'::jsonb,
    matched       jsonb not null default '{}'::jsonb,
    error         text
);

create index if not exists idx_raw_site_fetches_account on raw_site_fetches(account_id);

comment on table raw_site_fetches is
    'Audit trail of Tier-2 website fetches: what was probed and what matched.';

-- keep updated_at fresh
drop trigger if exists trg_account_signals_updated_at on account_signals;
create trigger trg_account_signals_updated_at
    before update on account_signals
    for each row execute function set_updated_at();

-- RLS: server-side pipeline only (service-role key bypasses RLS)
alter table account_signals  enable row level security;
alter table raw_site_fetches enable row level security;
