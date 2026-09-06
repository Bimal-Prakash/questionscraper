"""Shorthand for `python cli.py extract`.

Kept because it is the entry point the README has always pointed at. All the
logic lives in cli.py so the two cannot drift apart.

  python extract.py                 # pull until Ctrl+C, into the database
  python extract.py --count 20      # pull 20 new questions and stop
  python extract.py --json out.json # pull into a flat JSON file instead
"""

import sys

from cli import main as cli_main

if __name__ == "__main__":
    sys.argv.insert(1, "extract")
    cli_main()
