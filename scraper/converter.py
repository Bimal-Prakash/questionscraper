import re
from bs4 import BeautifulSoup, NavigableString, Tag

def html_to_markdown(html_content: str) -> str:
    """
    Converts problem statement HTML from LeetCode or HackerRank into clean,
    properly formatted GitHub-flavored Markdown.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script, style, and MathJax SVG styling tags that pollute text
    for tag in soup(["script", "style", "svg"]):
        tag.decompose()

    # Pre-process mathjax / math elements if present
    for math in soup.find_all(class_=re.compile(r"math|MathJax", re.I)):
        annotation = math.find("annotation")
        if annotation and annotation.string:
            math.replace_with(f"`{annotation.string.strip()}`")

    def process_node(node) -> str:
        if isinstance(node, NavigableString):
            # Normalize non-breaking spaces and whitespace
            text = str(node).replace("\xa0", " ")
            return text

        if not isinstance(node, Tag):
            return ""

        tag_name = node.name.lower()
        inner = "".join(process_node(child) for child in node.children)

        if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag_name[1])
            return f"\n\n{'#' * level} {inner.strip()}\n\n"

        elif tag_name == "p":
            return f"\n\n{inner.strip()}\n\n"

        elif tag_name in ["strong", "b"]:
            # Avoid duplicate bolding if already surrounded by spaces
            stripped = inner.strip()
            if not stripped:
                return ""
            return f"**{stripped}** "

        elif tag_name in ["em", "i"]:
            stripped = inner.strip()
            if not stripped:
                return ""
            return f"*{stripped}* "

        elif tag_name == "code":
            # If parent is a pre tag, don't double wrap backticks
            if node.parent and node.parent.name == "pre":
                return inner
            # Single-line inline code
            clean = inner.strip().replace("\n", " ")
            if not clean:
                return ""
            return f"`{clean}`"

        elif tag_name == "pre":
            code_text = node.get_text().strip()
            return f"\n\n```text\n{code_text}\n```\n\n"

        elif tag_name in ["ul", "ol"]:
            items = []
            is_ordered = tag_name == "ol"
            idx = 1
            for child in node.children:
                if isinstance(child, Tag) and child.name == "li":
                    item_text = "".join(process_node(c) for c in child.children).strip()
                    prefix = f"{idx}. " if is_ordered else "- "
                    items.append(f"{prefix}{item_text}")
                    idx += 1
            return "\n\n" + "\n".join(items) + "\n\n"

        elif tag_name == "li":
            return inner.strip()

        elif tag_name == "sup":
            return f"^{inner.strip()}"

        elif tag_name == "sub":
            return f"_{inner.strip()}"

        elif tag_name == "br":
            return "\n"

        elif tag_name == "hr":
            return "\n\n---\n\n"

        elif tag_name == "a":
            href = node.get("href", "")
            return f"[{inner.strip()}]({href})"

        elif tag_name == "img":
            src = node.get("src", "")
            alt = node.get("alt", "image")
            return f"![{alt}]({src})"

        elif tag_name in ["div", "section", "article"]:
            return f"\n{inner}\n"

        return inner

    markdown = process_node(soup)

    # Clean up excessive newlines & trailing spaces
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    # Clean up spaces around bold/italic and punctuation
    markdown = re.sub(r"\s+([,\.\?\!])", r"\1", markdown)
    markdown = markdown.strip()

    return markdown
