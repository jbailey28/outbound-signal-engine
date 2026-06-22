# Deploying the daily run to DigitalOcean

Goal: every weekday morning, the server refreshes triggers, re-ranks accounts,
drafts the top 5, and posts them to your Discord channel — automatically,
whether or not your laptop is on.

`scripts/daily.py` is the single entry point cron calls. It runs:
triggers → score → draft top 5 → post to Discord.

---

## 1. Create / pick a Droplet

A small Ubuntu droplet is plenty (the cheapest shared-CPU tier works).
SSH in as a non-root sudo user:

```bash
ssh youruser@YOUR_DROPLET_IP
```

## 2. Install prerequisites

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
```

## 3. Clone the repo

```bash
git clone https://github.com/jbailey28/outbound-signal-engine.git
cd outbound-signal-engine
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 4. Add the files git doesn't carry (secrets + your real config)

These are gitignored on purpose, so copy them up from your Mac. From your
**laptop** (new terminal), in the project folder:

```bash
# secrets
scp .env youruser@YOUR_DROPLET_IP:~/outbound-signal-engine/.env

# your real Awin templates + client roster + style guide
scp -r data/reference youruser@YOUR_DROPLET_IP:~/outbound-signal-engine/data/reference
```

> Without `data/reference/email_config.json` the script falls back to the
> committed sample config (fictional brands) — so this copy step is required
> for real Awin drafts.

`.env` must contain: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`DISCORD_WEBHOOK_URL`, and your draft provider's creds (`ANTHROPIC_API_KEY`,
or Ollama settings). Add `DRAFT_PROVIDER=claude` to pick the default provider.

## 5. Test it once by hand

```bash
cd ~/outbound-signal-engine && . .venv/bin/activate
python scripts/daily.py
```

You should see the steps run and "posted N Discord messages" — check Discord.

## 6. Schedule it with cron

Cron on the droplet runs in **UTC**. Pick your local time accordingly
(e.g. 7:00 AM US-Eastern = 11:00 or 12:00 UTC depending on DST). Weekdays only:

```bash
mkdir -p ~/outbound-signal-engine/logs
crontab -e
```

Add this line (12:00 UTC, Mon–Fri):

```cron
0 12 * * 1-5 cd /home/youruser/outbound-signal-engine && /home/youruser/outbound-signal-engine/.venv/bin/python scripts/daily.py >> logs/daily.log 2>&1
```

Save and exit. Check it's registered: `crontab -l`. Logs land in
`logs/daily.log`.

---

## Updating later

When you change the code, on the droplet:

```bash
cd ~/outbound-signal-engine && git pull && . .venv/bin/activate && pip install -r requirements.txt
```

Re-copy `data/reference/` or `.env` only if those changed locally.

## Adding new accounts

Import + load run on your **laptop** (they need the Salesforce PDF and your
CSV review). After loading new accounts to Supabase, the droplet's next daily
run picks them up automatically — no redeploy needed.

## Cost note

The daily run hits Google News (free) and your draft provider. On Claude
(`claude-opus-4-8`) the 5 drafts cost a few cents/day. To run free, set
`DRAFT_PROVIDER=ollama` and run Ollama on the droplet (needs a larger droplet
with enough RAM for the model).
