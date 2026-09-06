# ⚡ Question Extractor (LeetCode & HackerRank)

> Continuously harvests coding questions from **LeetCode** and **HackerRank**
> into Postgres (or SQLite locally), with **strict zero-duplicate guarantees**,
> and serves them as a JSON API your frontend can call.

Deployment on free tiers — Neon + Render + GitHub Actions — is in
**[DEPLOY.md](DEPLOY.md)**.

---

## 🌟 Key Features

- **Continuous Extraction**: keeps pulling questions from both platforms until you press **Stop** (UI) or `Ctrl+C` (CLI), or until a `--count` / `--minutes` budget runs out.
- **Durable Storage**: every problem statement, difficulty, tag, constraint, hint, test case and multi-language code snippet lands in the database as it arrives. No file to lose, no partial write.
- **Zero Duplicates Ever**: enforced by a unique constraint on `(platform, slug)`, so even two harvesters running at once cannot double-store a question. An in-memory index on top of it avoids the wasted fetch.
- **Resumable**: the catalogue cursor lives in the database, so a scheduled run picks up where the last one stopped instead of re-walking pages.
- **JSON API**: filter by platform, difficulty, tag or search term; stream the whole dataset back out as `questions.json` whenever you want the flat file.
- **Start / Stop Dashboard**: live counters and an activity feed at `/`.

---

## 🚀 Quick Start

Everything below writes to `data/questions.db` (SQLite) unless `DATABASE_URL`
points somewhere else. Copy `.env.example` to `.env` to change any setting.

```bash
pip install -r requirements.txt
```

### 1. Harvest questions

```bash
python cli.py extract                 # pull until Ctrl+C
python cli.py extract --count 25      # pull 25 new questions, then stop
python cli.py extract --minutes 20    # pull for 20 minutes (what CI runs)
python cli.py extract --json out.json # pull into a flat JSON file instead
```

`python extract.py` is a shorthand for `python cli.py extract`.

### 2. Launch the dashboard

```bash
python cli.py serve --port 8000       # or: python app.py
```

Open **`http://127.0.0.1:8000`**:

1. **▶ Start Extraction** begins the continuous pull.
2. Live counters (Total, LeetCode, HackerRank, Duplicates Skipped) and the
   question stream update as it runs.
3. **⏹ Stop Extraction** halts it.
4. **Download questions.json** streams the whole dataset out of the database.

When `ADMIN_TOKEN` is set (every deployed environment), the dashboard shows an
**Admin token** field under the controls; paste the token there and Start, Stop
and Reset work. It is read straight off the field on each request and stored
nowhere - closing the tab forgets it. The field stays hidden locally, where no
token is configured.

### 3. Other commands

```bash
python cli.py stats                      # what is stored, and the catalogue cursor
python cli.py import-json questions.json # seed the database from a JSON file
python cli.py export-json backup.json    # dump the database back to a JSON file
python cli.py fetch two-sum              # store one specific problem
python cli.py fetch https://www.hackerrank.com/challenges/simple-array-sum/problem
```

---

## 🌐 API

```
GET  /api/questions?platform=leetcode&difficulty=Easy&tag=Array&q=sum&limit=50&offset=0
GET  /api/questions/{platform}/{slug}
GET  /api/questions/download
GET  /api/stats
GET  /health
GET  /docs                        interactive OpenAPI docs
```

Mutating endpoints (`POST /api/extractor/start`, `/stop`, `POST /api/fetch`,
`DELETE /api/questions`) require `X-Admin-Token` whenever `ADMIN_TOKEN` is set.

`summary_only=true` on `/api/questions` drops descriptions, snippets and test
cases — enough to render a list, roughly 50x smaller.

---

## 📄 Question Schema

The API and `export-json` both emit this shape (`questions.json` in the repo is
the same format, and is what `import-json` reads):

```json
[
  {
    "id": "1",
    "title": "Two Sum",
    "slug": "two-sum",
    "platform": "leetcode",
    "url": "https://leetcode.com/problems/two-sum/",
    "difficulty": "Easy",
    "category": "Algorithms",
    "tags": ["Array", "Hash Table"],
    "description_html": "<p>You are given an array of integers...</p>",
    "description_markdown": "You are given an array of integers `nums`...",
    "constraints": ["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9"],
    "hints": ["A really brute force way would be to search for all possible pairs..."],
    "sample_test_cases": [{ "input": "[2,7,11,15]\n9", "output": "[0,1]" }],
    "code_snippets": [
      {
        "lang": "Python3",
        "lang_slug": "python3",
        "code": "class Solution:\n    def twoSum(self, nums: List[int], target: int) -> List[int]:\n        pass"
      }
    ],
    "metadata": {}
  }
]
```

---

## 📁 Project Structure

```
questionscraper/
├── app.py                # FastAPI: read API, extractor controls, dashboard
├── cli.py                # extract / stats / import-json / export-json / fetch / serve
├── extract.py            # shorthand for `cli.py extract`
├── config.py             # environment-driven settings
├── db.py                 # engine, session factory, schema bootstrap
├── db_models.py          # questions + extractor_state tables
├── questions.json        # seed dataset, imported with `cli.py import-json`
├── render.yaml           # Render blueprint (free tier)
├── DEPLOY.md             # Neon + Render + GitHub Actions walkthrough
├── .github/workflows/
│   └── scrape.yml        # scheduled harvest into Neon
├── scraper/              # core extraction library
│   ├── db_store.py       # DbProblemStore - durable, zero-duplicate storage
│   ├── storage.py        # JsonProblemStore - flat questions.json alternative
│   ├── extractor.py      # ContinuousExtractor background coordinator
│   ├── leetcode.py       # LeetCode GraphQL catalog & problem extractor
│   ├── hackerrank.py     # HackerRank REST catalog & problem extractor
│   ├── models.py         # Problem & snippet Pydantic models
│   ├── converter.py      # HTML-to-Markdown parser
│   └── client.py         # unified problem fetcher
└── static/               # dashboard UI
    ├── index.html
    ├── css/styles.css
    └── js/app.js
```
