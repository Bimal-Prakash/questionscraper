import sys
import time
import signal
import argparse
from pathlib import Path
from scraper import ContinuousExtractor, JsonProblemStore, fetch_problem

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(
        description="Continuous Question Extractor — Pulls questions from LeetCode & HackerRank into questions.json without duplicates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage:
  # Keep pulling questions continuously until you press Ctrl+C:
  python extract.py

  # Pull up to 20 questions into questions.json and stop:
  python extract.py --count 20

  # Save to a custom JSON file:
  python extract.py --output my_questions.json
        """
    )
    parser.add_argument(
        "--output", "-o",
        default="questions.json",
        help="Path to output JSON file (default: questions.json)"
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=0,
        help="Target number of new questions to extract before stopping (0 = pull indefinitely until Ctrl+C)"
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=0.8,
        help="Polite delay in seconds between question requests (default: 0.8s)"
    )
    parser.add_argument(
        "--single", "-s",
        help="Optional: Extract a single specific problem by URL or slug into the JSON dataset"
    )

    args = parser.parse_args()

    store = JsonProblemStore(file_path=args.output)
    initial_stats = store.get_stats()

    print("=" * 65)
    print("⚡ CONTINUOUS CODING QUESTION EXTRACTOR (LEETCODE & HACKERRANK)")
    print("=" * 65)
    print(f"Output File:        {store.file_path}")
    print(f"Existing in JSON:   {initial_stats['total_questions']} questions "
          f"({initial_stats['leetcode_count']} LeetCode, {initial_stats['hackerrank_count']} HackerRank)")
    print(f"Extraction Target:  {'Infinite (pulls until Ctrl+C)' if args.count == 0 else f'{args.count} new questions'}")
    print("=" * 65)

    if args.single:
        print(f"[*] Extracting single problem: {args.single}...")
        try:
            prob = fetch_problem(args.single)
            added = store.add_problem(prob)
            if added:
                print(f"[+] Saved '{prob.title}' ({prob.platform.value.upper()}) to {args.output}")
            else:
                print(f"[SKIP] Problem '{prob.title}' already exists in {args.output}")
        except Exception as e:
            print(f"[!] Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

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

    # Graceful Ctrl+C handling
    def sigint_handler(sig, frame):
        print("\n\n[*] Stop signal received (Ctrl+C). Halting extraction...")
        extractor.stop()

    signal.signal(signal.SIGINT, sigint_handler)

    print("[*] Starting continuous pulling loop... Press Ctrl+C at any time to stop.\n")
    extractor.start()

    try:
        while extractor.is_running:
            time.sleep(0.3)
    except KeyboardInterrupt:
        extractor.stop()

    # Final summary
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

if __name__ == "__main__":
    main()
