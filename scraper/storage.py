import json
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Union
from scraper.models import Problem, Platform

def make_problem_key(platform: str, slug: str) -> str:
    plat_str = str(platform).lower().replace("platform.", "").strip()
    slug_str = str(slug).lower().strip()
    return f"{plat_str}:{slug_str}"

class JsonProblemStore:
    """
    Manages persistent JSON storage with strict deduplication for extracted questions.
    Guarantees no duplicate questions are saved to questions.json.
    """
    def __init__(self, file_path: Union[str, Path] = "questions.json"):
        self.file_path = Path(file_path).resolve()
        self.problems: List[Dict[str, Any]] = []
        self.seen_keys: Set[str] = set()
        self.seen_urls: Set[str] = set()
        self.duplicates_skipped: int = 0
        self.load()

    def load(self) -> None:
        """
        Loads existing questions from the JSON file and populates the deduplication index.
        """
        self.problems = []
        self.seen_keys = set()
        self.seen_urls = set()

        if not self.file_path.exists():
            return

        try:
            content = self.file_path.read_text(encoding="utf-8")
            if not content.strip():
                return
            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        plat = item.get("platform", "")
                        slug = item.get("slug", "")
                        url = item.get("url", "")
                        if slug:
                            self.seen_keys.add(make_problem_key(plat, slug))
                        if url:
                            self.seen_urls.add(url.lower().rstrip("/"))
                        self.problems.append(item)
        except Exception as e:
            print(f"[Warning] Could not parse existing {self.file_path}: {e}")

    def has_problem(self, platform: str, slug: str, url: Optional[str] = None) -> bool:
        """
        Checks whether a problem is already stored in the JSON file.
        """
        key = make_problem_key(platform, slug)
        if key in self.seen_keys:
            return True
        if url and url.lower().rstrip("/") in self.seen_urls:
            return True
        return False

    def add_problem(self, problem: Union[Problem, Dict[str, Any]]) -> bool:
        """
        Adds a problem to the store and saves to disk immediately.
        Returns True if added, False if it was a duplicate and skipped.
        """
        if isinstance(problem, Problem):
            prob_dict = problem.model_dump()
            plat = problem.platform.value if hasattr(problem.platform, "value") else str(problem.platform)
            slug = problem.slug
            url = problem.url
        else:
            prob_dict = dict(problem)
            plat = str(prob_dict.get("platform", ""))
            slug = str(prob_dict.get("slug", ""))
            url = str(prob_dict.get("url", ""))

        if self.has_problem(plat, slug, url):
            self.duplicates_skipped += 1
            return False

        key = make_problem_key(plat, slug)
        self.seen_keys.add(key)
        if url:
            self.seen_urls.add(url.lower().rstrip("/"))

        self.problems.append(prob_dict)
        self.save()
        return True

    def save(self) -> None:
        """
        Atomically saves the question dataset to the JSON file.
        """
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(self.problems, indent=2, ensure_ascii=False)

        # Write to temporary file first then replace to avoid partial writes
        temp_dir = self.file_path.parent
        fd, temp_file_path = tempfile.mkstemp(dir=temp_dir, prefix="questions_tmp_", text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)

        # Atomic replace on Windows/POSIX
        try:
            os.replace(temp_file_path, self.file_path)
        except Exception:
            # Fallback direct write if os.replace fails
            self.file_path.write_text(serialized, encoding="utf-8")
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass

    def get_stats(self) -> Dict[str, int]:
        """
        Returns stats about total questions, breakdown by platform, and skipped duplicates.
        """
        lc_count = 0
        hr_count = 0
        for p in self.problems:
            plat = str(p.get("platform", "")).lower()
            if "leetcode" in plat:
                lc_count += 1
            elif "hackerrank" in plat:
                hr_count += 1

        return {
            "total_questions": len(self.problems),
            "leetcode_count": lc_count,
            "hackerrank_count": hr_count,
            "duplicates_skipped": self.duplicates_skipped,
        }

    def get_all(self) -> List[Dict[str, Any]]:
        return list(self.problems)

    def clear(self) -> None:
        self.problems = []
        self.seen_keys = set()
        self.seen_urls = set()
        self.duplicates_skipped = 0
        self.save()
