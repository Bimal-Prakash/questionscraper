# ⚡ Question Extractor (LeetCode & HackerRank)

> An automated coding question extractor that continuously harvests questions from **LeetCode** and **HackerRank** directly into a clean `questions.json` format until you press **Stop**, with **strict zero-duplicate guarantees**.

---

## 🌟 Key Features

- **Continuous Extraction**: Keeps pulling questions automatically from LeetCode and HackerRank until you press **Stop** (in the UI) or `Ctrl+C` (in CLI).
- **Pure JSON Storage**: All problem statements, difficulty, tags, constraints, hints, test cases, and multi-language code snippets are saved directly into `questions.json`.
- **Zero Duplicates Ever**: Every question is deduplicated across sessions by unique `(platform, slug)` identity before fetching and saving.
- **Zero Input Required**: You don't have to choose a platform or type problem names like `two-sum`. The tool continuously extracts any available problems automatically.
- **Start / Stop Controls**: Simple, responsive Start & Stop buttons with real-time counters and a live activity feed.
- **Direct JSON Download**: 1-click download of the complete `questions.json` dataset right from the dashboard.

---

## 🚀 Quick Start

### 1. Run the CLI Extractor (Continuous Mode)

Extract questions continuously into `questions.json` until you press `Ctrl+C`:

```bash
python extract.py
```

Or extract a specific target count:
```bash
# Pull 25 new questions and then stop automatically
python extract.py --count 25

# Save into a custom JSON file
python extract.py --output dataset.json
```

Or via the CLI runner:
```bash
python cli.py extract
python cli.py extract --count 50
```

---

### 2. Launch the Web UI with Start/Stop Controls

Launch the interactive control dashboard:

```bash
python app.py
```
Or:
```bash
python cli.py serve --port 8000
```

Open **`http://127.0.0.1:8000`** in your browser:
1. Click **▶ Start Extraction** to begin continuously pulling questions.
2. Watch the live counters (Total, LeetCode, HackerRank, Duplicates Skipped) and live question stream update in real-time.
3. Click **⏹ Stop Extraction** at any time to pause or halt.
4. Click **Download questions.json** or **View JSON** to preview and export your dataset.

---

### 3. Fetch an Individual Problem into JSON (Optional)

If you ever want to add a specific problem by URL or slug:
```bash
python cli.py fetch two-sum
python cli.py fetch https://www.hackerrank.com/challenges/simple-array-sum/problem
```

---

## 📄 Output Schema (`questions.json`)

Each question in `questions.json` contains:

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
    "sample_test_cases": [
      {
        "input": "[2,7,11,15]\n9",
        "output": "[0,1]"
      }
    ],
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
├── extract.py            # Standalone continuous CLI extractor
├── cli.py                # Command-line interface with subcommands
├── app.py                # FastAPI server with Start/Stop & JSON endpoints
├── questions.json        # Unified master JSON question dataset
├── test_extractor.py     # Automated tests for extractor & deduplication
├── scraper/              # Core extraction library
│   ├── storage.py        # JsonProblemStore with zero-duplicate index
│   ├── extractor.py      # ContinuousExtractor background coordinator
│   ├── leetcode.py       # LeetCode GraphQL catalog & problem extractor
│   ├── hackerrank.py     # HackerRank REST catalog & problem extractor
│   ├── models.py         # Problem & snippet Pydantic models
│   ├── converter.py      # HTML-to-Markdown parser
│   └── client.py         # Unified problem fetcher
└── static/               # Control dashboard UI
    ├── index.html        # Start/Stop console & live stream
    ├── css/styles.css    # Modern dark mode glassmorphic styling
    └── js/app.js         # Real-time controller & poller
```
