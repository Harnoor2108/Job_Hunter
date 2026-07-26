# Job Hunter

Automated job search pipeline: fetches fresh LinkedIn postings via Apify,
scores them against your resume/skills profile, and writes ranked results
to a Google Sheet — twice a day, on GitHub's servers, with no local machine
needed once it's set up.

## How it works

1. `configs/harnoor.json` — a static file describing target roles, location,
   weighted skills, and filtering rules. Edit this by hand whenever your
   search criteria change.
2. `scripts/fetch_jobs.py` — calls an Apify LinkedIn Jobs Scraper actor
   filtered to postings from the last 24 hours, then double-checks each one
   against LinkedIn's guest job-posting page to drop closed listings.
3. `scripts/score_jobs.py` — scores each posting 0–100 based on skill
   keyword matches (weighted), a title-match bonus, and an
   over-experience penalty. Drops anything below `min_match_score`.
4. `scripts/push_to_sheets.py` — upserts the ranked list into today's tab
   of your Google Sheet, keyed by apply link so re-runs update existing
   rows instead of duplicating them.
5. `.github/workflows/job-hunter.yml` — runs steps 2–4 automatically at
   ~5am and ~5pm Eastern every day via GitHub Actions.

## One-time setup

### 1. Apify
- Get an API token from https://console.apify.com/account/integrations
- You'll add this as a GitHub secret in step 4 below (and optionally to a
  local `.env` for testing).

### 2. Google service account
1. Google Cloud Console — create or reuse a project
2. Enable the Google Sheets API and Google Drive API
3. Create a service account, generate a JSON key, download it
4. Base64-encode it:
   ```
   base64 -i path/to/service-account.json | tr -d '\n'
   ```
5. Create a Google Sheet (e.g., "Job Hunter Results")
6. Share the sheet with the service account's `client_email`, Editor access
7. Copy the Sheet ID from the URL (`.../d/<SHEET_ID>/edit`)

### 3. Local testing (optional but recommended before automating)
```
cp example.env .env
# fill in APIFY_TOKEN, JSON_KEY_BASE_64, SHEET_ID in .env
pip install -r requirements.txt

python scripts/fetch_jobs.py configs/harnoor.json
python scripts/score_jobs.py configs/harnoor.json
python scripts/push_to_sheets.py configs/harnoor.json
```
Check your Sheet for a new tab dated today with ranked results.

### 4. GitHub Actions setup (for automatic twice-daily runs)
In your repo: Settings → Secrets and variables → Actions → New repository secret.
Add three secrets:
- `APIFY_TOKEN`
- `JSON_KEY_BASE_64`
- `SHEET_ID`

Push this repo to GitHub. The workflow in `.github/workflows/job-hunter.yml`
will then run automatically at the scheduled times, and you can also
trigger it manually anytime from the repo's Actions tab
(`workflow_dispatch`).

## Known limitations to be aware of

- **Daylight saving time drift.** GitHub Actions cron runs in UTC. The
  schedule in this repo is tuned for Eastern Daylight Time (summer). When
  clocks fall back to EST in November, runs will land an hour earlier
  (~4am/4pm) until clocks spring forward again in March. Harmless for a
  job feed, but worth knowing.
- **GitHub may pause schedules on inactive repos.** Scheduled workflows on
  repos with no commits for ~60 days can be automatically disabled. An
  occasional config tweak or manual run resets that clock.
- **Apify actor input schemas can change.** `fetch_jobs.py` targets
  `curious_coder/linkedin-jobs-scraper`'s real input schema as of when this
  was written (an array of pre-built LinkedIn search URLs, one per target
  role, plus `count`/`scrapeCompany`/`useIncognitoMode`). If Apify updates
  that actor's schema, check https://apify.com/curious_coder/linkedin-jobs-scraper/input
  and adjust `build_actor_input()` / `build_search_url()` accordingly.
- **`scrapeCompany` is off by default** in this config to keep runs fast and
  cheap. Set it to `True` in `fetch_jobs.py` if you want employer metadata
  (company size, description, etc.) at the cost of slower, pricier runs.
- **Score is a heuristic, not a guarantee.** Keyword matching is a rough
  proxy for fit — always skim actual postings before applying, especially
  ones scored right at your `min_match_score` cutoff.

## Updating your search criteria

Edit `configs/harnoor.json` directly and commit the change — no need to
re-run any setup steps. The next scheduled (or manual) run picks up the
new criteria automatically.
