import argparse
import sys
import webbrowser
import time
import signal
from scraper import (
    fetch_problem,
    JsonProblemStore,
    ContinuousExtractor,
    Platform
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def run_extract_command(args):
    store = JsonProblemStore(file_path=args.output)
    initial_stats = store.get_stats()

    print("=" * 65)
    print("⚡ CONTINUOUS CODING QUESTION EXTRACTOR")
    print("=" * 65)
    print(f"Output File:        {store.file_path}")
    print(f"Existing in JSON:   {initial_stats['total_questions']} questions "
          f"({initial_stats['leetcode_count']} LeetCode, {initial_stats['hackerrank_count']} HackerRank)")
    print(f"Extraction Target:  {'Infinite (pulls until Ctrl+C)' if args.count == 0 else f'{args.count} new questions'}")
    print("=" * 65)

    extracted_count = 0
    target_count = args.count

    def on_extracted(item):
        nonlocal extracted_count
        extracted_count += 1
        plat = item['platform'].upper()
        diff = item.get('difficulty', 'Unknown')
        tags = ', '.join(item.get('tags', [])[:3])
        tag_str = f" [{tags}]" if tags else ""
        print(f"[+] [{plat}] ({extracted_count}) Extracted: {item['title']} - {diff}{tag_str}")

        if target_count > 0 and extracted_count >= target_count:
            print(f"\n[*] Target count of {target_count} reached.")
            extractor.stop()

    def on_skipped(item):
        plat = item['platform'].upper()
        print(f"[-] [{plat}] Duplicate skipped: {item.get('title', item.get('slug'))}")

    extractor = ContinuousExtractor(
        store=store,
        delay_seconds=args.delay,
        on_item_extracted=on_extracted,
        on_duplicate_skipped=on_skipped,
    )

    def sigint_handler(sig, frame):
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

    final_stats = store.get_stats()
    print("\n" + "=" * 65)
    print("EXTRACTION SUMMARY")
    print("=" * 65)
    print(f"Questions Added This Session: {extracted_count}")
    print(f"Duplicates Skipped:           {store.duplicates_skipped}")
    print(f"Total Unique in JSON:         {final_stats['total_questions']}")
    print(f"  - LeetCode:                 {final_stats['leetcode_count']}")
    print(f"  - HackerRank:               {final_stats['hackerrank_count']}")
    print(f"File Saved At:                {store.file_path}")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(
        description="Question Scraper - Extract coding questions directly from LeetCode & HackerRank into JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Continuously pull questions into questions.json:
  python cli.py extract

  # Pull 25 new questions into questions.json:
  python cli.py extract --count 25

  # Fetch a specific problem into questions.json:
  python cli.py fetch two-sum --json

  # Launch the interactive Web UI dashboard with Start/Stop button:
  python cli.py serve --port 8000
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Extract command (Default)
    extract_parser = subparsers.add_parser("extract", help="Continuously extract questions into questions.json")
    extract_parser.add_argument("--output", "-o", default="questions.json", help="Output JSON path (default: questions.json)")
    extract_parser.add_argument("--count", "-n", type=int, default=0, help="Questions to extract (0 = infinite until Ctrl+C)")
    extract_parser.add_argument("--delay", "-d", type=float, default=0.8, help="Delay between requests (default: 0.8s)")

    # Fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch a single question by URL or slug")
    fetch_parser.add_argument("query", help="Problem URL or slug (e.g. 'two-sum' or full URL)")
    fetch_parser.add_argument(
        "--platform", "-p",
        choices=["auto", "leetcode", "hackerrank"],
        default="auto",
        help="Target platform (default: auto)"
    )
    fetch_parser.add_argument(
        "--json", "-j",
        action="store_true",
        default=True,
        help="Save directly to questions.json (default: true)"
    )
    fetch_parser.add_argument(
        "--output-json",
        default="questions.json",
        help="Path to questions.json file (default: questions.json)"
    )
    fetch_parser.add_argument(
        "--open-url",
        action="store_true",
        help="Open the original question URL in the web browser"
    )

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Launch the Web UI dashboard with Start/Stop controls")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    serve_parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")

    args = parser.parse_args()

    if not args.command or args.command == "extract":
        # If no arguments given, default to extract
        if not hasattr(args, "output"):
            args.output = "questions.json"
            args.count = 0
            args.delay = 0.8
        run_extract_command(args)
        return

    if args.command == "serve":
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8000)
        no_browser = getattr(args, "no_browser", False)

        url = f"http://{host}:{port}"
        print(f"[*] Starting Question Extractor Web UI at {url}")
        if not no_browser:
            webbrowser.open(url)

        import uvicorn
        from app import app
        uvicorn.run(app, host=host, port=port)
        return

    if args.command == "fetch":
        print(f"[*] Fetching problem '{args.query}' (Platform: {args.platform})...")
        try:
            problem = fetch_problem(args.query, platform=args.platform)
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

            if args.json:
                store = JsonProblemStore(file_path=args.output_json)
                added = store.add_problem(problem)
                if added:
                    print(f"[+] Successfully saved into {args.output_json} (Total: {len(store.problems)})")
                else:
                    print(f"[SKIP] Problem already exists in {args.output_json} (No duplicate added)")

        except Exception as e:
            print(f"[!] Error: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
