from bs4 import BeautifulSoup
import html
import re


def clean_html_text(html_content: str) -> str:
    """
    Convert HTML content into clean plain text.
    """

    if not html_content:
        return ""

    # Decode HTML entities such as &#39; → '
    html_content = html.unescape(html_content)

    # Parse HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Extract text while preserving readable separation
    text = soup.get_text(separator="\n")

    # Remove bullet characters
    text = text.replace("·", "")

    # Remove excessive whitespace
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    # Join the cleaned lines
    text = "\n".join(lines)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()