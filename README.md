# outbound-signal-engine

An outbound intelligence system for sales prospecting. It analyzes an account
book, detects affiliate/partner-program signals, checks for recent business
triggers, scores accounts, and (in later milestones) drafts first-touch emails —
so a rep can prioritize the **5 best accounts to reach out to each day** instead
of researching every account by hand.

> Built as a live portfolio project. Designed to be modular, auditable, and
> safe-by-default: no automated outreach, no AI-generated email until a human has
> reviewed the underlying data.

## Why this exists

Manual first-touch research is the slowest part of outbound. For each account a
rep has to: figure out whether the prospect runs an affiliate/partner program,
figure out *which platform* they run it on, find a recent trigger (news,
earnings, hiring, product launch), and only then write a relevant first email.

This system automates the **research and prioritization**, leaving the rep to do
the high-value part: the actual sequencing and relationship-building.

## Roadmap

| Milestone | Scope | Status |
|-----------|-------|--------|
| **M1 — Account Book Import** | Parse Salesforce Printable-View PDFs → normalize domains → dedupe → clean CSV + audit trail → Supabase schema | ✅ in progress |
| M2 — Affiliate/Partner Signal Detection | Scrape account websites for affiliate-program / platform signals | planned |
| M3 — Trigger Detection | Recent news / economic / hiring triggers per account | planned |
| M4 — Account Scoring | Rank accounts; surface the daily top 5 | planned |
| M5 — First-Touch Draft Generation | Draft (not send) emails from signals + triggers + sample messaging | planned |

## Milestone 1 — Account Book Import (this milestone)

Reliable import layer that turns a Salesforce **Printable View PDF** into clean,
deduplicated account data, while preserving the raw rows for audit.

> **Parsing note:** Salesforce Printable-View PDFs draw the table with
> horizontal row rules but *no vertical column rules*, so naive cell extraction
> collapses all five columns into one. The parser instead reconstructs columns
> from word x-positions: it finds each column's header anchor and assigns every
> word to the rightmost column whose left edge it has reached. Validated on a
> real 65-account export (65/65 accounts, all domains resolved).

### What it does

1. Accepts a Salesforce Printable-View PDF
2. Extracts account rows (Account Name, Website, Competitors, Industry, Sub-Industry)
3. Normalizes website URLs into clean domains
4. Deduplicates on website domain (falls back to account name when no website)
5. Stores raw imported rows for audit
6. Stores cleaned accounts in a usable table
7. Tracks each import batch
8. Produces a clean CSV for review **before** anything is inserted into Supabase

### What it deliberately does NOT do yet

- No AI email generation
- No automated outreach
- No Salesforce API integration
- No contact enrichment
- No automatic DB writes — CSV review gate comes first

## Quick start

```bash
# 1. install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. run against the bundled synthetic sample (no real data needed)
python scripts/import_accounts.py data/sample/sample_accounts.pdf

# 3. run against a real Salesforce Printable-View PDF
python scripts/import_accounts.py data/raw_pdfs/my_export.pdf

# outputs land in data/output/:
#   <batch>__accounts_clean.csv   <- review this
#   <batch>__raw_rows.csv         <- audit trail
#   <batch>__manifest.json        <- batch metadata
```

Nothing is written to Supabase by this script. Loading the reviewed CSV into
Supabase is a separate, explicit step (see `db/schema.sql`).

## Project layout

```
outbound-signal-engine/
├── README.md
├── requirements.txt
├── .env.example                 # config template (never commit real secrets)
├── .gitignore                   # raw PDFs + outputs + secrets stay local
├── db/
│   └── schema.sql               # Supabase / Postgres schema (3 tables)
├── src/outbound_signal_engine/
│   ├── domains.py               # URL -> clean domain normalization
│   ├── pdf_import.py            # geometry-based Salesforce PDF -> rows
│   ├── accounts.py              # clean + dedupe + batch logic
│   └── config.py                # expected columns + settings
├── scripts/
│   └── import_accounts.py       # CLI entry point
├── tests/
│   ├── test_domains.py
│   └── make_sample_pdf.py       # generates the synthetic sample PDF
└── data/
    ├── raw_pdfs/                # your real PDFs (gitignored)
    ├── sample/                  # synthetic demo PDF (committed)
    └── output/                  # generated CSVs (gitignored)
```

## Data model

Three tables, raw and clean kept separate (see `db/schema.sql`):

- **`import_batches`** — one row per PDF import (filename, content hash, counts, status)
- **`raw_account_rows`** — exactly what came out of the PDF, per batch, for audit
- **`accounts`** — cleaned, deduplicated accounts keyed by `domain`

## Privacy / safety

Real account data never enters git. `data/raw_pdfs/` and `data/output/` are
gitignored; only the synthetic sample is committed. Secrets live in `.env`
(also gitignored). The repo is safe to make public.
