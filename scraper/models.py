from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Platform(str, Enum):
    LEETCODE = "leetcode"
    HACKERRANK = "hackerrank"
    AUTO = "auto"

class Difficulty(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    UNKNOWN = "Unknown"

class CodeSnippet(BaseModel):
    lang: str
    lang_slug: str
    code: str

class TestCase(BaseModel):
    input: str
    output: Optional[str] = None
    explanation: Optional[str] = None

class Problem(BaseModel):
    id: str = Field(..., description="Problem ID or number")
    title: str = Field(..., description="Title of the problem")
    slug: str = Field(..., description="URL slug of the problem")
    platform: Platform = Field(..., description="leetcode or hackerrank")
    url: str = Field(..., description="Canonical URL to the problem")
    difficulty: Difficulty = Field(default=Difficulty.UNKNOWN)
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    description_html: str = Field(default="", description="Original HTML problem statement")
    description_markdown: str = Field(default="", description="Cleaned Markdown representation")
    constraints: List[str] = Field(default_factory=list)
    hints: List[str] = Field(default_factory=list)
    sample_test_cases: List[TestCase] = Field(default_factory=list)
    code_snippets: List[CodeSnippet] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
