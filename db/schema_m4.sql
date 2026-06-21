-- outbound-signal-engine — Milestone 4 schema (account scoring)
-- Target: Supabase / Postgres. Run after db/schema.sql and db/schema_m2.sql.
--
-- One current opportunity score per account. Score = fit_score (+ trigger_score
-- once M3 lands). Ranking is ORDER BY total_score desc at query time, so we
-- never store a brittle rank integer.

create extension if not exists "pgcrypto";

create table if not exists account_scores (
    id            uuid primary key default gen_random_uuid(),
    account_id    uuid not null references accounts(id) on delete cascade,

    -- opportunity segment derived from the affiliate signal
    --   'greenfield'           = no program found        -> highest opportunity
    --   'non_impact_platform'  = on a competitor/in-house program (switchable)
    --   'on_impact'            = already on Impact        -> lowest opportunity
    --   'unknown'              = signal unresolved (manual review)
    segment       text not null,

    fit_score     integer not null default 0,   -- from segment (0-100)
    trigger_score integer not null default 0,   -- timing bonus (M3, later)
    total_score   integer not null default 0,   -- fit_score + trigger_score
    needs_review  boolean not null default false,

    reasons       jsonb not null default '{}'::jsonb,  -- explainability

    scored_at     timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- one current score per account (upsert target)
create unique index if not exists uq_account_scores_account on account_scores(account_id);
create index if not exists idx_account_scores_total on account_scores(total_score desc);
create index if not exists idx_account_scores_segment on account_scores(segment);

comment on table account_scores is
    'Current opportunity score per account. total_score = fit + trigger; rank by it.';

drop trigger if exists trg_account_scores_updated_at on account_scores;
create trigger trg_account_scores_updated_at
    before update on account_scores
    for each row execute function set_updated_at();

alter table account_scores enable row level security;

-- ---------------------------------------------------------------------------
-- Convenience view: the daily prioritization list (accounts + signal + score).
-- Later (lifecycle feature) this will also filter to status = 'active'.
-- ---------------------------------------------------------------------------
create or replace view daily_prospects as
select
    a.id            as account_id,
    a.account_name,
    a.domain,
    a.industry,
    s.platform,
    s.has_program,
    sc.segment,
    sc.total_score,
    sc.needs_review
from accounts a
left join account_signals s
    on s.account_id = a.id and s.signal_type = 'affiliate_program'
left join account_scores sc
    on sc.account_id = a.id
order by sc.total_score desc nulls last, a.account_name;

comment on view daily_prospects is
    'Joined prioritization view: account + affiliate signal + opportunity score.';
