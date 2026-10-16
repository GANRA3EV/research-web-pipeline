"""Извлечение текста и контроль пригодности полученной страницы."""
import hashlib
from bs4 import BeautifulSoup


def extract(html: str, source: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "template"]):
        node.decompose()
    title_node = soup.select_one(source.get("title_selector", "title"))
    nodes = soup.select(source.get("text_selector", "body"))
    text = "\n".join(" ".join(node.stripped_strings) for node in nodes).strip()
    return {
        "title": title_node.get_text(" ", strip=True) if title_node else "",
        "text": text,
        "word_count": len(text.split()),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "quality": "ok" if text else "empty_selection",
    }
