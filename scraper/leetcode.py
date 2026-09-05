import re
from typing import Optional, List, Dict, Any
import httpx
from scraper.models import Problem, Platform, Difficulty, CodeSnippet, TestCase
from scraper.converter import html_to_markdown

GRAPHQL_URL = "https://leetcode.com/graphql"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://leetcode.com",
    "Origin": "https://leetcode.com",
}

QUESTION_QUERY = """
query getQuestionDetail($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    titleSlug
    difficulty
    categoryTitle
    content
    sampleTestCase
    exampleTestcaseList
    hints
    topicTags {
      name
      slug
    }
    codeSnippets {
      lang
      langSlug
      code
    }
  }
}
"""

LIST_QUESTIONS_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total: totalNum
    questions: data {
      questionFrontendId
      title
      titleSlug
      difficulty
      isPaidOnly
      topicTags {
        name
        slug
      }
    }
  }
}
"""

def list_leetcode_problems(
    limit: int = 50,
    skip: int = 0,
    category: str = "",
    free_only: bool = True,
    timeout: float = 12.0
) -> List[Dict[str, Any]]:
    """
    Fetches a page of problem summaries from LeetCode catalog.
    """
    payload = {
        "query": LIST_QUESTIONS_QUERY,
        "variables": {
            "categorySlug": category,
            "limit": limit,
            "skip": skip,
            "filters": {}
        }
    }

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(GRAPHQL_URL, json=payload, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

    raw_list = data.get("data", {}).get("problemsetQuestionList", {}).get("questions", [])
    results: List[Dict[str, Any]] = []

    for item in raw_list:
        if free_only and item.get("isPaidOnly"):
            continue
        results.append({
            "id": str(item.get("questionFrontendId") or ""),
            "title": item.get("title", ""),
            "slug": item.get("titleSlug", ""),
            "difficulty": item.get("difficulty", "Unknown"),
            "is_paid": bool(item.get("isPaidOnly", False)),
            "platform": "leetcode",
            "url": f"https://leetcode.com/problems/{item.get('titleSlug')}/",
            "tags": [t.get("name") for t in item.get("topicTags", []) if t.get("name")],
        })

    return results

def extract_leetcode_slug(input_str: str) -> str:
    """
    Extracts the problem slug from either a URL or raw slug string.
    Examples:
      - https://leetcode.com/problems/two-sum/ -> two-sum
      - https://leetcode.com/problems/two-sum/description/ -> two-sum
      - two-sum -> two-sum
    """
    cleaned = input_str.strip().strip("/")
    match = re.search(r"leetcode\.com/problems/([^/?#]+)", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    # If no URL pattern matched, treat entire string as slug
    return cleaned.split("/")[-1].lower()

def parse_difficulty(diff_str: Optional[str]) -> Difficulty:
    if not diff_str:
        return Difficulty.UNKNOWN
    val = diff_str.capitalize()
    if val in ["Easy", "Medium", "Hard"]:
        return Difficulty(val)
    return Difficulty.UNKNOWN

def extract_sample_test_cases(sample_test_case: Optional[str], example_list: Optional[List[str]]) -> List[TestCase]:
    test_cases: List[TestCase] = []
    if example_list:
        for ex in example_list:
            if ex:
                test_cases.append(TestCase(input=ex.strip()))
    elif sample_test_case:
        test_cases.append(TestCase(input=sample_test_case.strip()))
    return test_cases

def extract_constraints(markdown_content: str) -> List[str]:
    constraints = []
    match = re.search(r"###?\s*Constraints:?(.*?)(?=###|\Z)", markdown_content, re.DOTALL | re.IGNORECASE)
    if match:
        block = match.group(1)
        for line in block.split("\n"):
            cleaned = line.strip().lstrip("-*•").strip()
            if cleaned and not cleaned.lower().startswith("constraints"):
                constraints.append(cleaned)
    return constraints

def fetch_leetcode_problem(url_or_slug: str, timeout: float = 12.0) -> Problem:
    """
    Fetches a LeetCode problem by URL or slug via LeetCode's public GraphQL API.
    """
    slug = extract_leetcode_slug(url_or_slug)
    if not slug:
        raise ValueError(f"Could not extract a valid LeetCode slug from '{url_or_slug}'")

    payload = {
        "query": QUESTION_QUERY,
        "variables": {"titleSlug": slug}
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(GRAPHQL_URL, json=payload, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Failed to communicate with LeetCode API: {e}") from e

    question_data = data.get("data", {}).get("question")
    if not question_data:
        raise ValueError(f"Problem '{slug}' not found on LeetCode or response was empty.")

    title = question_data.get("title", slug.replace("-", " ").title())
    frontend_id = question_data.get("questionFrontendId") or question_data.get("questionId") or ""
    difficulty = parse_difficulty(question_data.get("difficulty"))
    category = question_data.get("categoryTitle", "Algorithms")
    html_content = question_data.get("content") or ""
    markdown_content = html_to_markdown(html_content)

    tags = [t.get("name") for t in question_data.get("topicTags", []) if t.get("name")]
    hints = question_data.get("hints") or []

    # Code snippets
    raw_snippets = question_data.get("codeSnippets") or []
    snippets = [
        CodeSnippet(
            lang=s.get("lang", ""),
            lang_slug=s.get("langSlug", ""),
            code=s.get("code", "")
        )
        for s in raw_snippets if s.get("code")
    ]

    sample_cases = extract_sample_test_cases(
        question_data.get("sampleTestCase"),
        question_data.get("exampleTestcaseList")
    )
    constraints = extract_constraints(markdown_content)

    return Problem(
        id=str(frontend_id),
        title=title,
        slug=slug,
        platform=Platform.LEETCODE,
        url=f"https://leetcode.com/problems/{slug}/",
        difficulty=difficulty,
        category=category,
        tags=tags,
        description_html=html_content,
        description_markdown=markdown_content,
        constraints=constraints,
        hints=hints,
        sample_test_cases=sample_cases,
        code_snippets=snippets,
        metadata={
            "raw_id": question_data.get("questionId"),
            "category": category,
        }
    )
