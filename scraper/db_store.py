"""Postgres/SQLite-backed problem store.

Same surface as `JsonProblemStore` - `has_problem`, `add_problem`, `get_stats`,
`clear` - so the extractor does not know or care which one it was handed. The
difference is where the zero-duplicate guarantee comes from: the JSON store
relies entirely on its in-process index, while here that index only saves a
network fetch. The real guarantee is the unique constraint on (platform, slug),
which holds even when a GitHub Actions run and the API host scrape at once.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Iterator, Sequence

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from db import SessionLocal
from db_models import ExtractorState, Question
from scraper.models import Problem

logger = logging.getLogger(__name__)

CURSOR_KEY = "catalog_cursor"


def make_problem_key(platform: str, slug: str) -> str:
    plat_str = str(platform).lower().replace("platform.", "").strip()
    return f"{plat_str}:{str(slug).lower().strip()}"


def tags_index(tags: Any) -> str:
    """Pipe-delimited, lowercased tag list for the `tags_text` LIKE filter."""
    values = [str(t).strip().lower() for t in (tags or []) if str(t).strip()]
    return "|" + "|".join(values) + "|" if values else ""


def _normalize(problem: Problem | dict[str, Any]) -> dict[str, Any]:
    """Flatten either input form into the column set `Question` expects."""
    if isinstance(problem, Problem):
        data = problem.model_dump(mode="json")
    else:
        data = dict(problem)

    platform = str(data.get("platform", "")).lower().replace("platform.", "").strip()
    difficulty = str(data.get("difficulty", "Unknown")).replace("Difficulty.", "")

    return {
        "external_id": str(data.get("id") or ""),
        "platform": platform,
        "slug": str(data.get("slug") or "").strip(),
        "title": str(data.get("title") or "")[:512],
        "url": str(data.get("url") or "").strip(),
        "difficulty": difficulty or "Unknown",
        "category": data.get("category"),
        "tags": data.get("tags") or [],
        "tags_text": tags_index(data.get("tags")),
        "description_html": data.get("description_html") or "",
        "description_markdown": data.get("description_markdown") or "",
        "constraints": data.get("constraints") or [],
        "hints": data.get("hints") or [],
        "sample_test_cases": data.get("sample_test_cases") or [],
        "code_snippets": data.get("code_snippets") or [],
        "extra": data.get("metadata") or {},
    }


class DbProblemStore:
    """Durable question storage with strict deduplication."""

    def __init__(self, warm_index: bool = True):
        self.duplicates_skipped: int = 0
        self._lock = threading.Lock()
        self.seen_keys: set[str] = set()
        self.seen_urls: set[str] = set()
        if warm_index:
            self.load()

    # ------------------------------------------------------------- index
    def load(self) -> None:
        """Pull the identity columns into memory so catalogue walks are cheap.

        Three short columns per row, next to descriptions and code snippets
        that make up almost all of a stored question.
        """
        with SessionLocal() as session:
            rows = session.execute(
                select(Question.platform, Question.slug, Question.url)
            ).all()

        self.seen_keys = {make_problem_key(p, s) for p, s, _ in rows}
        self.seen_urls = {u.lower().rstrip("/") for _, _, u in rows if u}

    def has_problem(self, platform: str, slug: str, url: str | None = None) -> bool:
        if make_problem_key(platform, slug) in self.seen_keys:
            return True
        return bool(url) and url.lower().rstrip("/") in self.seen_urls

    # -------------------------------------------------------------- write
    def add_problem(self, problem: Problem | dict[str, Any]) -> bool:
        """Insert one problem. Returns False when it was already stored."""
        row = _normalize(problem)
        if not row["slug"] or not row["platform"]:
            raise ValueError("A problem needs both a platform and a slug")

        key = make_problem_key(row["platform"], row["slug"])
        url_key = row["url"].lower().rstrip("/")

        with self._lock:
            if key in self.seen_keys or (url_key and url_key in self.seen_urls):
                self.duplicates_skipped += 1
                return False

        try:
            with SessionLocal() as session:
                session.add(Question(**row))
                session.commit()
        except IntegrityError:
            # Another writer inserted the same problem between the index check
            # and the commit. Not an error - the constraint doing its job.
            with self._lock:
                self.duplicates_skipped += 1
                self.seen_keys.add(key)
                if url_key:
                    self.seen_urls.add(url_key)
            return False

        with self._lock:
            self.seen_keys.add(key)
            if url_key:
                self.seen_urls.add(url_key)
        return True

    def add_many(self, problems: Sequence[Problem | dict[str, Any]]) -> int:
        """Bulk path for the JSON import. Returns the number inserted."""
        added = 0
        for problem in problems:
            try:
                if self.add_problem(problem):
                    added += 1
            except ValueError as exc:
                logger.warning("Skipped a malformed problem: %s", exc)
        return added

    def save(self) -> None:
        """No-op. Every write is committed already; kept for interface parity."""

    def clear(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(Question))
            session.execute(delete(ExtractorState))
            session.commit()
        with self._lock:
            self.seen_keys.clear()
            self.seen_urls.clear()
            self.duplicates_skipped = 0

    # --------------------------------------------------------------- read
    def get_stats(self) -> dict[str, int]:
        with SessionLocal() as session:
            rows = session.execute(
                select(Question.platform, func.count()).group_by(Question.platform)
            ).all()
        counts = {str(platform): int(count) for platform, count in rows}
        return {
            "total_questions": sum(counts.values()),
            "leetcode_count": counts.get("leetcode", 0),
            "hackerrank_count": counts.get("hackerrank", 0),
            "duplicates_skipped": self.duplicates_skipped,
        }

    def query(
        self,
        offset: int = 0,
        limit: int = 50,
        platform: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        summary_only: bool = False,
    ) -> tuple[int, list[dict[str, Any]]]:
        """One page of questions plus the total the filters match."""
        stmt = select(Question)
        if platform:
            stmt = stmt.where(Question.platform == platform.lower())
        if difficulty:
            stmt = stmt.where(Question.difficulty == difficulty.capitalize())
        if tag:
            stmt = stmt.where(Question.tags_text.like(f"%|{tag.strip().lower()}|%"))
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(Question.title.ilike(pattern), Question.slug.ilike(pattern))
            )

        with SessionLocal() as session:
            total = session.execute(
                select(func.count()).select_from(stmt.subquery())
            ).scalar_one()
            rows = (
                session.execute(stmt.order_by(Question.id).offset(offset).limit(limit))
                .scalars()
                .all()
            )
            items = [row.to_dict(summary=summary_only) for row in rows]

        return total, items

    def get_by_slug(self, platform: str, slug: str) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = session.execute(
                select(Question).where(
                    Question.platform == platform.lower(), Question.slug == slug
                )
            ).scalar_one_or_none()
            return row.to_dict() if row else None

    def iter_all(self, chunk_size: int = 200) -> Iterator[dict[str, Any]]:
        """Stream every question, a chunk at a time.

        The dataset is tens of megabytes of problem statements; the download
        endpoint uses this so a full export is never materialised in memory on
        a 512MB instance.
        """
        with SessionLocal() as session:
            stream = session.execute(
                select(Question)
                .order_by(Question.id)
                .execution_options(yield_per=chunk_size)
            ).scalars()
            for row in stream:
                yield row.to_dict()

    def get_all(self) -> list[dict[str, Any]]:
        """Every question in one list. Prefer `query` or `iter_all`."""
        return list(self.iter_all())

    def count(self) -> int:
        with SessionLocal() as session:
            return int(
                session.execute(select(func.count()).select_from(Question)).scalar_one()
            )

    # ------------------------------------------------------------- cursor
    def get_cursor(self) -> dict[str, Any]:
        with SessionLocal() as session:
            row = session.get(ExtractorState, CURSOR_KEY)
            return dict(row.value) if row and row.value else {}

    def set_cursor(self, cursor: dict[str, Any]) -> None:
        with SessionLocal() as session:
            row = session.get(ExtractorState, CURSOR_KEY)
            if row is None:
                session.add(ExtractorState(key=CURSOR_KEY, value=cursor))
            else:
                row.value = cursor
            session.commit()
