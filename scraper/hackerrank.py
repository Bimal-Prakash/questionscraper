import re
from typing import Optional, List, Dict, Any
import httpx
from scraper.models import Problem, Platform, Difficulty, CodeSnippet, TestCase
from scraper.converter import html_to_markdown

BASE_URL = "https://www.hackerrank.com/rest/contests/master/challenges"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

LANGUAGE_MAP = {
    "python3": ("Python 3", "python3"),
    "python": ("Python 2", "python"),
    "cpp": ("C++", "cpp"),
    "cpp14": ("C++14", "cpp14"),
    "cpp20": ("C++20", "cpp20"),
    "java": ("Java", "java"),
    "java8": ("Java 8", "java8"),
    "java15": ("Java 15", "java15"),
    "javascript": ("JavaScript", "javascript"),
    "typescript": ("TypeScript", "typescript"),
    "go": ("Go", "go"),
    "rust": ("Rust", "rust"),
    "c": ("C", "c"),
    "csharp": ("C#", "csharp"),
    "ruby": ("Ruby", "ruby"),
    "swift": ("Swift", "swift"),
    "kotlin": ("Kotlin", "kotlin"),
    "scala": ("Scala", "scala"),
}

def list_hackerrank_problems(
    limit: int = 50,
    offset: int = 0,
    track: Optional[str] = "algorithms",
    timeout: float = 12.0
) -> List[Dict[str, Any]]:
    """
    Fetches a page of challenge summaries from HackerRank catalog.
    """
    if track:
        endpoint = f"https://www.hackerrank.com/rest/contests/master/tracks/{track}/challenges"
    else:
        endpoint = "https://www.hackerrank.com/rest/contests/master/challenges"

    params = {"offset": offset, "limit": limit}

    with httpx.Client(timeout=timeout) as client:
        resp = client.get(endpoint, params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

    raw_models = data.get("models", [])
    results: List[Dict[str, Any]] = []

    for item in raw_models:
        slug = item.get("slug")
        if not slug:
            continue
        results.append({
            "id": str(item.get("id") or ""),
            "title": item.get("name") or slug.replace("-", " ").title(),
            "slug": slug,
            "difficulty": item.get("difficulty_name") or "Unknown",
            "platform": "hackerrank",
            "url": f"https://www.hackerrank.com/challenges/{slug}/problem",
            "max_score": item.get("max_score"),
        })

    return results

def extract_hackerrank_slug(input_str: str) -> str:
    """
    Extracts the challenge slug from URL or string.
    Examples:
      - https://www.hackerrank.com/challenges/simple-array-sum/problem -> simple-array-sum
      - https://www.hackerrank.com/challenges/simple-array-sum -> simple-array-sum
      - simple-array-sum -> simple-array-sum
    """
    cleaned = input_str.strip().strip("/")
    match = re.search(r"hackerrank\.com/challenges/([^/?#]+)", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return cleaned.split("/")[-1].lower()

def parse_difficulty(diff_str: Optional[str]) -> Difficulty:
    if not diff_str:
        return Difficulty.UNKNOWN
    val = diff_str.strip().capitalize()
    if val in ["Easy", "Medium", "Hard"]:
        return Difficulty(val)
    return Difficulty.UNKNOWN

def fetch_hackerrank_problem(url_or_slug: str, timeout: float = 12.0) -> Problem:
    """
    Fetches a HackerRank challenge by URL or slug via the HackerRank REST API.
    """
    slug = extract_hackerrank_slug(url_or_slug)
    if not slug:
        raise ValueError(f"Could not extract a valid HackerRank slug from '{url_or_slug}'")

    endpoint = f"{BASE_URL}/{slug}"

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(endpoint, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Failed to communicate with HackerRank API: {e}") from e

    model = data.get("model")
    if not model:
        raise ValueError(f"Problem '{slug}' not found on HackerRank or response was empty.")

    title = model.get("name", slug.replace("-", " ").title())
    prob_id = str(model.get("id") or "")
    difficulty = parse_difficulty(model.get("difficulty_name"))
    category = model.get("category", "Algorithms")

    # Tags / topics
    tags = []
    if model.get("topics"):
        for t in model.get("topics", []):
            if isinstance(t, str):
                tags.append(t)
            elif isinstance(t, dict) and "name" in t:
                tags.append(t["name"])
    if model.get("track") and isinstance(model["track"], dict):
        track_name = model["track"].get("name")
        if track_name and track_name not in tags:
            tags.append(track_name)

    # Problem Statement & details
    body_html = model.get("body_html") or ""
    markdown_content = html_to_markdown(body_html)

    # Append input format, output format, and constraints if they exist separately
    sections = []
    if model.get("input_format"):
        sections.append(f"### Input Format\n\n{html_to_markdown(model['input_format'])}")
    if model.get("constraints"):
        sections.append(f"### Constraints\n\n{html_to_markdown(model['constraints'])}")
    if model.get("output_format"):
        sections.append(f"### Output Format\n\n{html_to_markdown(model['output_format'])}")

    if sections:
        extra_md = "\n\n".join(sections)
        if extra_md not in markdown_content:
            markdown_content = f"{markdown_content}\n\n{extra_md}".strip()

    # Constraints extraction
    constraints = []
    if model.get("constraints"):
        raw_c = html_to_markdown(model["constraints"])
        for line in raw_c.split("\n"):
            line_str = line.strip().lstrip("-*•").strip()
            if line_str:
                constraints.append(line_str)

    # Extract Code Snippets
    snippets: List[CodeSnippet] = []
    for key_prefix, (lang_name, lang_slug) in LANGUAGE_MAP.items():
        template_key = f"{key_prefix}_template"
        head_key = f"{key_prefix}_template_head"
        tail_key = f"{key_prefix}_template_tail"

        body_code = model.get(template_key) or ""
        head_code = model.get(head_key) or ""
        tail_code = model.get(tail_key) or ""

        # Assemble template code
        full_code = ""
        if head_code:
            full_code += head_code.strip() + "\n\n"
        if body_code:
            full_code += body_code.strip() + "\n"
        if tail_code:
            full_code += "\n" + tail_code.strip() + "\n"

        if full_code.strip():
            snippets.append(CodeSnippet(
                lang=lang_name,
                lang_slug=lang_slug,
                code=full_code.strip()
            ))

    # Test cases extraction from markdown examples if any
    sample_cases: List[TestCase] = []
    sample_match = re.findall(
        r"(?:Sample Input(?:\s*\d*)?|Example(?:\s*\d*)?)\s*[:\n]+```(?:text)?\n(.*?)\n```(?:\s*(?:Sample Output(?:\s*\d*)?)\s*[:\n]+```(?:text)?\n(.*?)\n```)?",
        markdown_content,
        re.DOTALL | re.IGNORECASE
    )
    for inp, outp in sample_match:
        sample_cases.append(TestCase(
            input=inp.strip(),
            output=outp.strip() if outp else None
        ))

    return Problem(
        id=prob_id,
        title=title,
        slug=slug,
        platform=Platform.HACKERRANK,
        url=f"https://www.hackerrank.com/challenges/{slug}/problem",
        difficulty=difficulty,
        category=category,
        tags=tags,
        description_html=body_html,
        description_markdown=markdown_content,
        constraints=constraints,
        hints=[],
        sample_test_cases=sample_cases,
        code_snippets=snippets,
        metadata={
            "max_score": model.get("max_score"),
            "success_ratio": model.get("success_ratio"),
        }
    )
