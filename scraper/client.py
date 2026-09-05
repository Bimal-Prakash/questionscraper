import re
from typing import Optional, Union
from scraper.models import Problem, Platform
from scraper.leetcode import fetch_leetcode_problem, extract_leetcode_slug
from scraper.hackerrank import fetch_hackerrank_problem, extract_hackerrank_slug

def detect_platform(url_or_slug: str, hint_platform: Optional[Union[str, Platform]] = None) -> Platform:
    """
    Detects which platform a given URL or query belongs to.
    """
    if hint_platform:
        if isinstance(hint_platform, str):
            hint_str = hint_platform.lower().strip()
            if hint_str == "leetcode":
                return Platform.LEETCODE
            elif hint_str == "hackerrank":
                return Platform.HACKERRANK
        elif hint_platform in [Platform.LEETCODE, Platform.HACKERRANK]:
            return hint_platform

    lower = url_or_slug.lower()
    if "leetcode.com" in lower:
        return Platform.LEETCODE
    if "hackerrank.com" in lower:
        return Platform.HACKERRANK

    # If ambiguous, return AUTO
    return Platform.AUTO

def fetch_problem(url_or_slug: str, platform: Optional[Union[str, Platform]] = Platform.AUTO) -> Problem:
    """
    Unified entry point to fetch a coding problem from either LeetCode or HackerRank.
    """
    resolved_platform = detect_platform(url_or_slug, platform)

    if resolved_platform == Platform.LEETCODE:
        return fetch_leetcode_problem(url_or_slug)
    elif resolved_platform == Platform.HACKERRANK:
        return fetch_hackerrank_problem(url_or_slug)
    else:
        # Platform.AUTO with a plain slug (not a full URL)
        # Try LeetCode first
        try:
            return fetch_leetcode_problem(url_or_slug)
        except Exception:
            # If LeetCode fails, try HackerRank
            try:
                return fetch_hackerrank_problem(url_or_slug)
            except Exception as hr_err:
                raise ValueError(
                    f"Could not find problem '{url_or_slug}' on either LeetCode or HackerRank. "
                    f"Please provide the full URL or specify the platform."
                ) from hr_err
