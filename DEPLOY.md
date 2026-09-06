# Deploying the API (free tier only)

Goal: a public HTTPS JSON API of coding questions your own frontend can call,
kept growing automatically. Three free services, no credit card.

| Piece | Runs on | Why there |
|---|---|---|
| Postgres | **Neon** free tier | Free hosts wipe their disk on every deploy, so a `questions.json` file or a SQLite database cannot survive one. 0.5GB holds well over 100k problem statements. |
| Harvester | **GitHub Actions** cron | Needs to run uninterrupted for tens of minutes at a polite request rate. A free web instance sleeps after 15 idle minutes, mid-loop. A CI runner does not, and costs nothing. |
| API | **Render** free web service | Reads Postgres, serves JSON, hosts the dashboard. |

The harvester and the API never talk to each other — they meet in the database.
That is what makes each piece small enough to fit in a free tier.

```
GitHub Actions (cron) ──writes──► Neon Postgres ◄──reads── Render API ◄── your frontend
```

---

## 1. Database — Neon

1. Sign up at <https://neon.tech> → **Create project**. Region: `AWS ap-southeast-1 (Singapore)`
   if you are in India, otherwise whichever is closest to you.
2. Copy the connection string. It looks like:

   ```
   postgresql://neondb_owner:npg_xxxx@ep-cool-name-123456.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
   ```

Paste that string verbatim wherever `DATABASE_URL` is asked for below. The app
rewrites the scheme for psycopg at startup (`config.py`) and passes `sslmode`
straight through, because psycopg is libpq-based and understands it. Tables are
created on first boot; later schema additions are applied automatically
(`db._sync_added_columns`).

Either endpoint works here — the direct one or the `-pooler` one. With the
pooler the app skips its own pool, since PgBouncer is already doing that job.

> Neon's free compute suspends after 5 minutes idle and wakes in under a second.
> The engine uses `pool_pre_ping` and a 280s recycle, so a suspended connection
> is replaced rather than raising.

## 2. API — Render

You do not need Docker. Render builds on its own machines, and `render.yaml`
uses their native Python runtime — a plain `pip install -r requirements.txt`.
`psycopg[binary]` ships a wheel, so nothing here needs a compiler or libpq.

1. <https://render.com> → **New → Blueprint** → connect this repo. It reads
   `render.yaml` and creates `question-scraper-api`.
2. Render prompts for the values marked `sync: false`:
   - `DATABASE_URL` — the Neon string.
   - `CORS_ORIGINS` — your frontend's origin(s), comma separated, scheme
     included, **no trailing slash**:
     `https://app.example.com,http://localhost:5173`
   - `CORS_ORIGIN_REGEX` — leave blank unless your frontend's hostname changes
     per deploy (preview builds). Example: `https://.*\.my-app\.vercel\.app`
3. After the first deploy, open **Environment** and copy the generated
   `ADMIN_TOKEN`. It is what the dashboard's Start/Stop buttons need.
4. Check it:

   ```bash
   curl https://<your-service>.onrender.com/health
   # {"status":"ok","database":true,"total_questions":0,...}
   ```

   Interactive docs at `/docs`, OpenAPI schema at `/openapi.json`, and the
   dashboard at `/`.

Two consequences of the free plan, both accounted for in the design:

- **It sleeps after 15 minutes of no traffic.** The request that wakes it waits
  ~40s; everything after is fast. Set your HTTP client's timeout to 60s and, if
  the delay matters, fire a throwaway `GET /health` when your app boots.
- **Do not run the harvest here.** `EXTRACT_ON_STARTUP` is `false` in
  `render.yaml` for that reason: a loop on an instance that sleeps mid-request
  is a stuttering scraper. The Start button still works for a manual top-up
  while you are watching it.

## 3. Harvester — GitHub Actions

Push the repo to GitHub, then **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `DATABASE_URL` | the Neon string from step 1 |

`.github/workflows/scrape.yml` then runs at 03:23 and 15:23 UTC, pulling for 20
minutes per run and remembering where it stopped in the catalogue.

Seed and smoke test in one go: **Actions → scrape → Run workflow**, tick
**seed** and set **minutes** to `2`. That imports the `questions.json` committed
to this repo (so the API has data immediately) and then harvests for two
minutes. It should finish with a non-zero total from `python cli.py stats`.
Leave **seed** off on every later run — it is idempotent, just pointless.

Minutes: unmetered on a public repo. On a private repo you get 2,000/month and
this schedule uses roughly 1,000.

---

## Order of operations

1. Neon → `DATABASE_URL`.
2. Render → deploy. Get the API URL and the generated `ADMIN_TOKEN`.
3. GitHub secret → run the workflow manually with **seed** ticked and `minutes=2`.
4. Point your frontend at the API URL; confirm `CORS_ORIGINS` matches its origin exactly.

---

## Calling it from your frontend

All read endpoints are public GETs with no auth. Full parameter list at `/docs`.

```
GET  /api/questions?platform=leetcode&difficulty=Easy&tag=Array&q=sum&limit=50&offset=0
GET  /api/questions/{platform}/{slug}     one question, in full
GET  /api/questions/download              the whole dataset as questions.json
GET  /api/stats                           totals per platform
GET  /health
```

Notes that matter when wiring this up:

- `limit` is capped at `MAX_PAGE_SIZE` (200); asking for more silently clamps.
  Page with `offset`, and read `total` from the response body.
- `summary_only=true` drops the description, snippets and test cases — roughly
  50x smaller, and enough to render a list.
- `tag` is an exact (case-insensitive) match on one topic tag, not a substring.
  `q` is the substring search, over title and slug.
- The download endpoint streams; it is one large JSON array, not paginated.

Mutating endpoints require `X-Admin-Token: <ADMIN_TOKEN>`:

```
POST   /api/extractor/start     start harvesting on the API host
POST   /api/extractor/stop
POST   /api/fetch               store one problem by URL or slug
DELETE /api/questions           delete everything
```

**Never put `ADMIN_TOKEN` in frontend code.** Anything shipped to a browser is
readable. The dashboard at `/` has an **Admin token** field under the controls:
paste the token there when you want to drive the extractor by hand. It is sent
as a header on that request and kept nowhere - not in the URL, not in browser
storage - so closing the tab forgets it. The cron keeps data growing without it.

---

## Working against the deployed database from your machine

```bash
export DATABASE_URL='postgresql://…?sslmode=require'   # PowerShell: $env:DATABASE_URL='…'
python cli.py stats
python cli.py import-json questions.json     # seed, idempotent
python cli.py extract --count 100            # harvest into Neon from here
python cli.py export-json backup.json        # pull the whole dataset back out
```

Without `DATABASE_URL` every command uses local SQLite at `data/questions.db`,
so the same commands are safe to try offline first.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `ModuleNotFoundError: psycopg` | `DATABASE_URL` points at Postgres but the install skipped `requirements.txt`. |
| `password authentication failed` | The Neon string was truncated — it ends at `channel_binding=require`, quote it in the shell. |
| CORS error in the browser | `CORS_ORIGINS` does not exactly match the browser's origin. Scheme included, no trailing slash, no path. |
| First request of the day hangs ~40s | Render free instance cold start. Expected. |
| `/health` says `"database": false` | Wrong `DATABASE_URL`, or the Neon project was deleted. |
| Render build fails on a wheel | `PYTHON_VERSION` in `render.yaml` is `3.12`; check it was not overridden in the dashboard. |
| `/api/questions` returns `total: 0` | The workflow has not run yet, or it failed. Check the Actions tab. |
| Start button returns 401 | The Admin token field is empty or holds the wrong value. Copy `ADMIN_TOKEN` from Render's Environment tab. |
| The harvest adds nothing new | Expected once the catalogue has been walked: the cursor is at the end and every candidate is already stored. It wraps around and re-checks cheaply. |
| A tag filter returns nothing for rows imported before this version | `tags_text` is written on insert; re-import those rows (`import-json`) to backfill it. |
