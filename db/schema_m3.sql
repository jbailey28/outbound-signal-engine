-- outbound-signal-engine — Milestone 3 schema (trigger detection)
-- Target: Supabase / Postgres. Run after schema.sql, schema_m2.sql, schema_m4.sql.
--
-- Triggers are recent newsworthy events (funding, acquisition, leadership hire,
-- launch, expansion, partnership) that make NOW a good time to reach out. Each
-- detected trigger article is stored for audit; the per-account trigger_score
-- is written back to account_scores (where total_score = fit + trigger).

create extension if not exists "pgcrypto";

create table if not exists account_triggers (
    id            uuid primary key default gen_random_uuid(),
    account_id    uuid not null references accounts(id) on delete cascade,

    trigger_type  text not null,        -- 'funding','acquisition','leadership',...
    title         text not null,
    url           text,
    published_at  timestamptz,
    source        text,                 -- which query/source surfaced it
    score         integer not null default 0,   -- this article's contribution

    detected_at   timestamptz not null default now()
);

create index if not exists idx_account_triggers_account on account_triggers(account_id);
create index if not exists idx_account_triggers_type on account_triggers(trigger_type);

-- de-dupe the same article for the same account across re-runs
create unique index if not exists uq_account_triggers_account_url
    on account_triggers(account_id, url) where url is not null;

comment on table account_triggers is
    'Recent newsworthy triggers per account (audit). Feeds account_scores.trigger_score.';

alter table account_triggers enable row level security;

-- The daily_prospects view (from schema_m4.sql) already reads account_scores,
-- so once trigger_score is written there the ranked list reflects triggers
-- automatically. No view change needed.
