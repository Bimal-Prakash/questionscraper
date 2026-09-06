"""ORM tables.

One row per problem, plus a tiny key/value table holding the extractor's
catalogue cursor. The cursor lives in the database rather than in memory
because the two processes that scrape (a GitHub Actions run and the API host)
are never the same process twice - an in-memory offset would restart at zero on
every deploy and re-walk pages that are already stored.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db import Base

# JSONB on Postgres (binary, indexable), plain JSON on SQLite.
JsonCol = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Question(Base):
    """A single coding problem, mirroring `scraper.models.Problem`."""

    __tablename__ = "questions"
    __table_args__ = (
        # The dedup guarantee. In-process sets are an optimisation on top of
        # this; the constraint is what survives two scrapers racing.
        UniqueConstraint("platform", "slug", name="uq_questions_platform_slug"),
        Index("ix_questions_platform_difficulty", "platform", "difficulty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The platform's own identifier ("1", "two-sum"'s frontend id, …). Not
    # unique across platforms, and not always present, so never a key.
    external_id: Mapped[str] = mapped_column(String(64), default="")
    platform: Mapped[str] = mapped_column(String(32), index=True)
    slug: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(512), index=True)
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    difficulty: Mapped[str] = mapped_column(String(32), default="Unknown", index=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tags: Mapped[list] = mapped_column(JsonCol, default=list)
    # The tag list again, lowercased and pipe-delimited ("|array|hash table|").
    # Filtering by tag is a LIKE against this instead of a JSON containment
    # query, which SQLite and Postgres spell differently - so one filter works
    # on both backends, in SQL, where it can be paginated correctly.
    tags_text: Mapped[str] = mapped_column(String(2048), default="", index=True)
    description_html: Mapped[str] = mapped_column(Text, default="")
    description_markdown: Mapped[str] = mapped_column(Text, default="")
    constraints: Mapped[list] = mapped_column(JsonCol, default=list)
    hints: Mapped[list] = mapped_column(JsonCol, default=list)
    sample_test_cases: Mapped[list] = mapped_column(JsonCol, default=list)
    code_snippets: Mapped[list] = mapped_column(JsonCol, default=list)
    # `metadata` is reserved by Declarative, so the column keeps the public
    # name and the attribute does not.
    extra: Mapped[dict] = mapped_column("metadata", JsonCol, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    def to_dict(self, summary: bool = False) -> dict:
        """Serialise back to the `questions.json` shape the clients expect."""
        base = {
            "id": self.external_id,
            "title": self.title,
            "slug": self.slug,
            "platform": self.platform,
            "url": self.url,
            "difficulty": self.difficulty,
            "category": self.category,
            "tags": self.tags or [],
        }
        if summary:
            return base
        base.update(
            {
                "description_html": self.description_html or "",
                "description_markdown": self.description_markdown or "",
                "constraints": self.constraints or [],
                "hints": self.hints or [],
                "sample_test_cases": self.sample_test_cases or [],
                "code_snippets": self.code_snippets or [],
                "metadata": self.extra or {},
            }
        )
        return base


class ExtractorState(Base):
    """Key/value scratch space for the catalogue cursor."""

    __tablename__ = "extractor_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JsonCol, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
