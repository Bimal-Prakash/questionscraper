"""Command line entry point.

Everything writes to the configured database (DATABASE_URL - SQLite locally,
Neon Postgres in production). `--json PATH` switches any command back to a flat
questions.json file for a throwaway local dataset.

  python cli.py extract --count 200        # harvest 200 new questions
  python cli.py extract --minutes 20       # harvest for 20 minutes (CI uses this)
  python cli.py stats                      # what is stored
  python cli.py import-json questions.json # seed the database from the repo file
  python cli.py export-json out.json       # dump the database back to a file
  python cli.py fetch two-sum              # store one specific problem
  python cli.py serve                      # local dashboard on :8000
"""

import argparse
import json
import signal
import sys
import time
import webbrowser
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def build_store(json_path: str | None):
    """Pick the storage backend for this invocation."""
    if json_path:
        from scraper import JsonProblemStore

        return JsonProblemStore(file_path=json_path)

    from db import init_db
    from scraper import DbProblemStore

    init_db()
    return DbProblemStore()


def describe_store(store) -> str:
    file_path = getattr(store, "file_path", None)
    if file_path is not None:
        return str(file_path)
    from db import describe_database

    return describe_database()


def run_extract_command(args) -> None:
    from scraper import ContinuousExtractor

    store = build_store(getattr(args, "json", None))
    initial = store.get_stats()

    if args.count:
        target = f"{args.count} new questions"
    elif args.minutes:
        target = f"{args.minutes} minutes of pulling"
    else:
        target = "Infinite (pulls until Ctrl+C)"

    print("=" * 65)
    print("CONTINUOUS CODING QUESTION EXTRACTOR")
    print("=" * 65)
    print(f"Storage:            {describe_store(store)}")
    print(f"Already stored:     {initial['total_questions']} questions "
          f"({initial['leetcode_count']} LeetCode, {initial['hackerrank_count']} HackerRank)")
    print(f"Extraction target:  {target}")
    print("=" * 65)

    extracted_count = 0

    def on_extracted(item):
        nonlocal extracted_count
        extracted_count += 1
        tags = ", ".join(item.get("tags", [])[:3])
        tag_str = f" [{tags}]" if tags else ""
        print(f"[+] [{item['platform'].upper()}] ({extracted_count}) "
              f"{item['title']} - {item.get('difficulty', 'Unknown')}{tag_str}", flush=True)

    def on_skipped(item):
        print(f"[-] [{item['platform'].upper()}] Duplicate skipped: "
              f"{item.get('title', item.get('slug'))}", flush=True)

    extractor = ContinuousExtractor(
        store=store,
        delay_seconds=args.delay,
        on_item_extracted=on_extracted,
        on_duplicate_skipped=on_skipped if args.verbose else None,
    )
    extractor.stop_after_items = max(0, args.count)
    extractor.stop_after_seconds = max(0.0, args.minutes * 60)

    def sigint_handler(_sig, _frame):
        print("\n\n[*] Stop signal received (Ctrl+C). Halting extraction...")
        extractor.stop()

    signal.signal(signal.SIGINT, sigint_handler)

    print("[*] Starting continuous extraction... Press Ctrl+C at any time to stop.\n")
    extractor.start()

    try:
        while extractor.is_running:
            time.sleep(0.3)
    except KeyboardInterrupt:
        extractor.stop()

    final = store.get_stats()
    print("\n" + "=" * 65)
    print("EXTRACTION SUMMARY")
    print("=" * 65)
    print(f"Added this session:  {extracted_count}")
    print(f"Duplicates skipped:  {store.duplicates_skipped}")
    print(f"Total stored:        {final['total_questions']}")
    print(f"  - LeetCode:        {final['leetcode_count']}")
    print(f"  - HackerRank:      {final['hackerrank_count']}")
    print(f"Storage:             {describe_store(store)}")
    print("=" * 65)


def run_stats_command(args) -> None:
    store = build_store(getattr(args, "json", None))
    stats = store.get_stats()
    print(f"Storage:      {describe_store(store)}")
    print(f"Total:        {stats['total_questions']}")
    print(f"  LeetCode:   {stats['leetcode_count']}")
    print(f"  HackerRank: {stats['hackerrank_count']}")

    cursor = getattr(store, "get_cursor", lambda: {})()
    if cursor:
        print(f"Catalog cursor: {cursor}")

    # Non-zero exit on an empty database makes a CI run fail loudly instead of
    # reporting success after scraping nothing.
    if stats["total_questions"] == 0:
        print("[!] No questions stored.", file=sys.stderr)
        sys.exit(1)


def run_import_command(args) -> None:
    """Seed the database from a questions.json file."""
    source = Path(args.path)
    if not source.exists():
        print(f"[!] No such file: {source}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print(f"[!] {source} is not a JSON array of questions.", file=sys.stderr)
        sys.exit(1)

    store = build_store(None)
    print(f"[*] Importing {len(data)} question(s) from {source} into {describe_store(store)}...")
    added = store.add_many(data)
    print(f"[+] Inserted {added}, skipped {len(data) - added} already present.")
    print(f"[*] Total stored: {store.get_stats()['total_questions']}")


def run_export_command(args) -> None:
    """Dump the database back out as a questions.json file."""
    store = build_store(None)
    target = Path(args.path)
    target.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with target.open("w", encoding="utf-8") as handle:
        handle.write("[\n")
        for item in store.iter_all():
            handle.write(("" if written == 0 else ",\n") + json.dumps(item, ensure_ascii=False, indent=2))
            written += 1
        handle.write("\n]\n")

    print(f"[+] Wrote {written} question(s) to {target}")


def run_fetch_command(args) -> None:
    from scraper import fetch_problem

    print(f"[*] Fetching problem '{args.query}' (platform: {args.platform})...")
    try:
        problem = fetch_problem(args.query, platform=args.platform)
    except Exception as e:
        print(f"[!] Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print(f"Title:       {problem.id}. {problem.title}")
    print(f"Platform:    {problem.platform.value.upper()}")
    print(f"Difficulty:  {problem.difficulty.value}")
    print(f"URL:         {problem.url}")
    print(f"Tags:        {', '.join(problem.tags) if problem.tags else 'None'}")
    print(f"Snippets:    {len(problem.code_snippets)} languages available")
    print("=" * 60)

    if args.open_url:
        webbrowser.open(problem.url)

    store = build_store(getattr(args, "json", None))
    if store.add_problem(problem):
        print(f"[+] Stored in {describe_store(store)}")
    else:
        print(f"[SKIP] Already present in {describe_store(store)} (no duplicate added)")


def run_serve_command(args) -> None:
    import uvicorn

    url = f"http://{args.host}:{args.port}"
    print(f"[*] Starting Question Extractor Web UI at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run("app:app", host=args.host, port=args.port)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Question Scraper - extract coding questions from LeetCode & HackerRank",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command")

    extract_parser = subparsers.add_parser("extract", help="Continuously extract questions")
    extract_parser.add_argument("--count", "-n", type=int, default=0,
                                help="Stop after this many new questions (0 = until Ctrl+C)")
    extract_parser.add_argument("--minutes", "-m", type=float, default=0,
                                help="Stop after this many minutes (0 = no limit)")
    extract_parser.add_argument("--delay", "-d", type=float, default=0.8,
                                help="Delay between requests (default: 0.8s)")
    extract_parser.add_argument("--json", help="Write to this JSON file instead of the database")
    extract_parser.add_argument("--verbose", "-v", action="store_true",
                                help="Also log every duplicate that was skipped")

    stats_parser = subparsers.add_parser("stats", help="Show what is stored")
    stats_parser.add_argument("--json", help="Read a JSON file instead of the database")

    import_parser = subparsers.add_parser("import-json", help="Seed the database from a JSON file")
    import_parser.add_argument("path", nargs="?", default="questions.json")

    export_parser = subparsers.add_parser("export-json", help="Dump the database to a JSON file")
    export_parser.add_argument("path", nargs="?", default="questions.export.json")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch a single question by URL or slug")
    fetch_parser.add_argument("query", help="Problem URL or slug (e.g. 'two-sum')")
    fetch_parser.add_argument("--platform", "-p", choices=["auto", "leetcode", "hackerrank"],
                              default="auto", help="Target platform (default: auto)")
    fetch_parser.add_argument("--json", help="Write to this JSON file instead of the database")
    fetch_parser.add_argument("--open-url", action="store_true",
                              help="Open the original question URL in a browser")

    serve_parser = subparsers.add_parser("serve", help="Launch the web dashboard")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--no-browser", action="store_true")

    args = parser.parse_args()

    if args.command in (None, "extract"):
        if args.command is None:
            args = extract_parser.parse_args([])
        run_extract_command(args)
    elif args.command == "stats":
        run_stats_command(args)
    elif args.command == "import-json":
        run_import_command(args)
    elif args.command == "export-json":
        run_export_command(args)
    elif args.command == "fetch":
        run_fetch_command(args)
    elif args.command == "serve":
        run_serve_command(args)


if __name__ == "__main__":
    main()
