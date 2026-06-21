-- outbound-signal-engine — Milestone 1 schema
-- Target: Supabase / Postgres
--
-- Design principle: raw data and cleaned data are kept SEPARATE.
--   import_batches   -> one row per PDF import (provenance + counts)
--   raw_account_rows -> exactly what came out of the PDF (audit, immutable)
--   accounts         -> cleaned, deduplicated account book (the usable table)
--
-- Run this in the Supabase SQL editor, or via `psql < db/schema.sql`.

-- Needed for gen_random_uuid()
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- 1. import_batches — track every PDF import
-- ---------------------------------------------------------------------------
create table if not exists import_batches (
    id              uuid primary key default gen_random_uuid(),
    source_filename text        not null,
    -- sha256 of the file bytes; lets us detect re-imports of the same PDF
    file_sha256     text        not null,
    imported_at     timestamptz not null default now(),
    -- counts captured at import time for quick auditing
    raw_row_count   integer     not null default 0,
    clean_row_count integer     not null default 0,
    status          text        not null default 'imported'
                    check (status in ('imported', 'reviewed', 'loaded', 'failed')),
    notes           text
);

comment on table import_batches is
    'One row per Salesforce Printable-View PDF import. Provenance + counts.';

-- ---------------------------------------------------------------------------
-- 2. raw_account_rows — immutable audit trail of what the PDF contained
-- ---------------------------------------------------------------------------
create table if not exists raw_account_rows (
    id            uuid primary key default gen_random_uuid(),
    batch_id      uuid not null references import_batches(id) on delete cascade,
    -- 0-based position of the row within the PDF (page order)
    row_index     integer,
    page_number   integer,
    -- raw, untouched cell values exactly as extracted
    account_name  text,
    website       text,
    competitors   text,
    industry      text,
    sub_industry  text,
    -- full original row as JSON, so we never lose anything even if columns shift
    raw           jsonb,
    created_at    timestamptz not null default now()
);

create index if not exists idx_raw_rows_batch on raw_account_rows(batch_id);

comment on table raw_account_rows is
    'Immutable copy of every extracted PDF row, for audit. Never edited in place.';

-- ---------------------------------------------------------------------------
-- 3. accounts — cleaned, deduplicated account book
-- ---------------------------------------------------------------------------
-- Dedup key (`dedup_key`) is always present and is the single source of truth:
--   * "domain:<registrable-domain>" when the account has a website
--   * "name:<normalized-name>"      when it doesn't
-- This collapses the domain-primary / name-fallback rule into ONE unique key,
-- which makes cross-import upserts a clean single ON CONFLICT path.
create table if not exists accounts (
    id               uuid primary key default gen_random_uuid(),
    account_name     text not null,
    website          text,           -- cleaned, canonical URL (https://domain)
    domain           text,           -- normalized registrable domain (for joins/queries)
    name_key         text not null,  -- normalized name
    dedup_key        text not null,  -- "domain:..." or "name:..." — UNIQUE
    competitors      text,
    industry         text,
    sub_industry     text,

    -- provenance: which batch first saw this account, and which last touched it
    first_seen_batch uuid references import_batches(id),
    last_seen_batch  uuid references import_batches(id),

    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

-- One account per dedup_key — the merge target for every re-import.
create unique index if not exists uq_accounts_dedup_key on accounts(dedup_key);

-- Non-unique index on domain for downstream lookups/joins (signals, scoring).
create index if not exists idx_accounts_domain
    on accounts(domain) where domain is not null;

comment on table accounts is
    'Cleaned, deduplicated account book. One row per dedup_key (domain or name).';

-- keep updated_at fresh on any change
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_accounts_updated_at on accounts;
create trigger trg_accounts_updated_at
    before update on accounts
    for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- Enable RLS on all three tables and add NO public policies. The importer
-- connects with the Supabase service-role key, which bypasses RLS, so the
-- pipeline keeps working — but the public anon/authenticated keys get zero
-- access to this internal account data. This is the safe default for a
-- server-side data pipeline (and for a public portfolio repo).
alter table import_batches   enable row level security;
alter table raw_account_rows enable row level security;
alter table accounts         enable row level security;

-- ---------------------------------------------------------------------------
-- Upsert reference (how the loader merges a reviewed CSV — single conflict key):
--
--   insert into accounts (account_name, website, domain, name_key, dedup_key,
--                         competitors, industry, sub_industry,
--                         first_seen_batch, last_seen_batch)
--   values (...)
--   on conflict (dedup_key) do update set
--       account_name    = excluded.account_name,
--       website         = excluded.website,
--       domain          = excluded.domain,
--       competitors     = excluded.competitors,
--       industry        = excluded.industry,
--       sub_industry    = excluded.sub_industry,
--       last_seen_batch = excluded.last_seen_batch;
-- ---------------------------------------------------------------------------
