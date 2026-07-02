# Junior SWE Job Alert Discord Bot

This project runs a fully scheduled job-alert pipeline on GitHub Actions. Every 30 minutes it polls several public job sources, filters for junior and new-grad software engineering roles, deduplicates against a committed SQLite state file, and posts only new matches to a Discord channel through a webhook. A second daily workflow discovers additional Greenhouse, Lever, and Workday sources through Brave Search so the polling coverage expands over time without requiring manual code changes.

## Setup

### 1. Create a Discord webhook

1. Open your Discord server settings.
2. Go to `Integrations` and create a new webhook for the channel that should receive job alerts.
3. Copy the webhook URL and save it for `DISCORD_WEBHOOK_URL`.

### 2. Get a Brave Search API key

1. Create a Brave Search API account.
2. Add a payment method to activate API access. At this query volume it should cost only fractions of a dollar per month.
3. Copy the API key and save it for `BRAVE_API_KEY`.

### 3. Get an Adzuna API key

1. Create a free developer account at Adzuna.
2. Copy the app ID and app key for `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`.

### 4. Add GitHub Actions secrets

In your GitHub repository, open `Settings -> Secrets and variables -> Actions` and add these four secrets:

- `DISCORD_WEBHOOK_URL`
- `BRAVE_API_KEY`
- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`

For local development, copy `.env.example` to `.env` and use the same variable names there.

## Local testing

1. Change into the generated repo:

```bash
cd job-alert-bot
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in whichever values you have available. Missing Adzuna or Brave keys only skip those specific integrations with warnings.

4. Run a dry run:

```bash
python main.py --dry-run
```

`--dry-run` executes the full fetch, filter, and dedupe pipeline, prints what would be sent, and does not post to Discord or write to the database.

To test source discovery locally:

```bash
python discover.py
```

## Tuning the sources and filters

Edit `config/companies.yaml` to add more direct Greenhouse and Lever company slugs. This is the manual seed list for companies you already know you want to watch.

Edit `config/filters.yaml` to loosen or tighten the junior-role matching rules. A title is kept only if it matches at least one include pattern and none of the exclude patterns.

Edit `config/discovery_queries.yaml` to add more Brave Search queries for discovering new Greenhouse, Lever, and Workday sources over time.

## How the workflows relate

`.github/workflows/check_jobs.yml` runs `main.py` every 30 minutes. It fetches jobs from configured Greenhouse and Lever boards, Adzuna, the SimplifyJobs new-grad repository, and any discovered Greenhouse, Lever, or Workday sources already stored in `db/jobs.sqlite`, then posts new matches to Discord and commits the updated `seen_jobs` state back to the repo.

`.github/workflows/discover_tenants.yml` runs `discover.py` once per day. It uses Brave Search to find new Greenhouse, Lever, and Workday job-board URLs, extracts the source metadata, stores any new sources in the same SQLite file, and commits the updated discovery state back to the repo.

Both workflows share the same `db-write` concurrency group so only one job writes `db/jobs.sqlite` at a time.
