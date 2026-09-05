import time
import threading
import traceback
from typing import Optional, Callable, Dict, Any, List
from scraper.models import Platform, Problem
from scraper.storage import JsonProblemStore
from scraper.leetcode import list_leetcode_problems, fetch_leetcode_problem
from scraper.hackerrank import list_hackerrank_problems, fetch_hackerrank_problem

class ContinuousExtractor:
    """
    Orchestrates continuous background pulling of coding problems from LeetCode
    and HackerRank into questions.json, with automatic deduplication and
    responsive start/stop controls.
    """
    def __init__(
        self,
        store: Optional[JsonProblemStore] = None,
        delay_seconds: float = 0.8,
        on_item_extracted: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_duplicate_skipped: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_status_change: Optional[Callable[[str], None]] = None,
    ):
        self.store = store or JsonProblemStore()
        self.delay_seconds = delay_seconds
        self.on_item_extracted = on_item_extracted
        self.on_duplicate_skipped = on_duplicate_skipped
        self.on_status_change = on_status_change

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.is_running: bool = False
        self.status_message: str = "Idle"
        self.current_action: str = ""
        self.recent_extracted: List[Dict[str, Any]] = []

        # Internal catalog pagination trackers
        self.lc_skip: int = 0
        self.hr_offset: int = 0
        self.hr_track_index: int = 0
        self.hr_tracks: List[str] = ["algorithms", "data-structures"]

    def start(self) -> bool:
        """
        Starts the continuous extraction worker thread if not already active.
        """
        with self._lock:
            if self.is_running:
                return False
            self._stop_event.clear()
            self.is_running = True
            self.status_message = "Running"
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

        if self.on_status_change:
            self.on_status_change(self.status_message)
        return True

    def stop(self) -> bool:
        """
        Signals the continuous extraction worker to halt.
        """
        with self._lock:
            if not self.is_running:
                return False
            self._stop_event.set()
            self.is_running = False
            self.status_message = "Stopped"
            self.current_action = "Stopped by user"

        if self.on_status_change:
            self.on_status_change(self.status_message)
        return True

    def get_state(self) -> Dict[str, Any]:
        """
        Returns full live state snapshot for UI and CLI reporting.
        """
        stats = self.store.get_stats()
        return {
            "is_running": self.is_running,
            "status": self.status_message,
            "current_action": self.current_action,
            "stats": stats,
            "recent_extracted": self.recent_extracted[:15],
        }

    def _run_loop(self) -> None:
        """
        Main extraction loop that keeps pulling questions until stopped.
        """
        turn = 0  # 0 for LeetCode, 1 for HackerRank

        try:
            while not self._stop_event.is_set():
                turn += 1
                if turn % 2 == 1:
                    # LeetCode Turn
                    self._pull_next_leetcode()
                else:
                    # HackerRank Turn
                    self._pull_next_hackerrank()

                if self._stop_event.is_set():
                    break

                time.sleep(self.delay_seconds)

        except Exception as e:
            traceback.print_exc()
            self.status_message = f"Error: {e}"
        finally:
            with self._lock:
                self.is_running = False
                if not self.status_message.startswith("Error"):
                    self.status_message = "Idle"
                self.current_action = ""

            if self.on_status_change:
                self.on_status_change(self.status_message)

    def _pull_next_leetcode(self) -> None:
        """
        Fetches next available non-duplicate LeetCode question.
        """
        self.current_action = f"Browsing LeetCode catalog (skip={self.lc_skip})..."
        try:
            candidates = list_leetcode_problems(limit=25, skip=self.lc_skip, free_only=True)
            if not candidates:
                # Wrap around or advance
                self.lc_skip = 0
                return
            self.lc_skip += len(candidates)
        except Exception as e:
            self.current_action = f"LeetCode catalog query failed: {e}"
            time.sleep(1.0)
            return

        for item in candidates:
            if self._stop_event.is_set():
                return

            slug = item["slug"]
            title = item.get("title", slug)

            # Deduplication Check
            if self.store.has_problem("leetcode", slug, item.get("url")):
                self.store.duplicates_skipped += 1
                if self.on_duplicate_skipped:
                    self.on_duplicate_skipped({
                        "platform": "leetcode",
                        "slug": slug,
                        "title": title,
                        "reason": "Already exists in questions.json"
                    })
                continue

            # Fetch Full Problem
            self.current_action = f"Extracting [LeetCode] {title}..."
            try:
                problem = fetch_leetcode_problem(slug)
                added = self.store.add_problem(problem)
                if added:
                    item_summary = {
                        "id": problem.id,
                        "title": problem.title,
                        "slug": problem.slug,
                        "platform": "leetcode",
                        "difficulty": problem.difficulty.value,
                        "url": problem.url,
                        "tags": problem.tags,
                        "test_cases_count": len(problem.sample_test_cases),
                        "snippets_count": len(problem.code_snippets),
                    }
                    self.recent_extracted.insert(0, item_summary)
                    if len(self.recent_extracted) > 50:
                        self.recent_extracted = self.recent_extracted[:50]

                    if self.on_item_extracted:
                        self.on_item_extracted(item_summary)

                    # Short breather between downloads
                    time.sleep(self.delay_seconds)
                    return  # Alternate to HackerRank
            except Exception as e:
                self.current_action = f"Error fetching [LeetCode] {slug}: {e}"
                time.sleep(0.5)

    def _pull_next_hackerrank(self) -> None:
        """
        Fetches next available non-duplicate HackerRank challenge.
        """
        track = self.hr_tracks[self.hr_track_index % len(self.hr_tracks)]
        self.current_action = f"Browsing HackerRank track '{track}' (offset={self.hr_offset})..."
        try:
            candidates = list_hackerrank_problems(limit=25, offset=self.hr_offset, track=track)
            if not candidates:
                # Advance track
                self.hr_track_index += 1
                self.hr_offset = 0
                return
            self.hr_offset += len(candidates)
        except Exception as e:
            self.current_action = f"HackerRank catalog query failed: {e}"
            time.sleep(1.0)
            return

        for item in candidates:
            if self._stop_event.is_set():
                return

            slug = item["slug"]
            title = item.get("title", slug)

            # Deduplication Check
            if self.store.has_problem("hackerrank", slug, item.get("url")):
                self.store.duplicates_skipped += 1
                if self.on_duplicate_skipped:
                    self.on_duplicate_skipped({
                        "platform": "hackerrank",
                        "slug": slug,
                        "title": title,
                        "reason": "Already exists in questions.json"
                    })
                continue

            # Fetch Full Problem
            self.current_action = f"Extracting [HackerRank] {title}..."
            try:
                problem = fetch_hackerrank_problem(slug)
                added = self.store.add_problem(problem)
                if added:
                    item_summary = {
                        "id": problem.id,
                        "title": problem.title,
                        "slug": problem.slug,
                        "platform": "hackerrank",
                        "difficulty": problem.difficulty.value,
                        "url": problem.url,
                        "tags": problem.tags,
                        "test_cases_count": len(problem.sample_test_cases),
                        "snippets_count": len(problem.code_snippets),
                    }
                    self.recent_extracted.insert(0, item_summary)
                    if len(self.recent_extracted) > 50:
                        self.recent_extracted = self.recent_extracted[:50]

                    if self.on_item_extracted:
                        self.on_item_extracted(item_summary)

                    # Short breather between downloads
                    time.sleep(self.delay_seconds)
                    return  # Alternate to LeetCode
            except Exception as e:
                self.current_action = f"Error fetching [HackerRank] {slug}: {e}"
                time.sleep(0.5)
