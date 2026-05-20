import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-ZA,en;q=0.9",
}

_PRICE_RE = re.compile(r"R\s?[\d\s,]+|\$\s?[\d,]+|£\s?[\d,]+|€\s?[\d,]+")


@dataclass
class GenericResult:
    site_name: str
    site_url: str
    title: str
    url: str
    price: str = field(default="")
    image_url: str = field(default="")


def scrape_site(url: str, keywords: list[str]) -> list[GenericResult]:
    """Fetch a page and return items whose text matches any of the given keywords."""
    domain = urlparse(url).netloc.replace("www.", "")
    kw_lower = [kw.lower() for kw in keywords]

    try:
        session = requests.Session()
        session.headers.update(_HEADERS)
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch %s: %s", url, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    # Remove non-content elements
    for tag in soup(["nav", "header", "footer", "script", "style", "meta", "noscript"]):
        tag.decompose()

    results: list[GenericResult] = []
    seen_titles: set[str] = set()

    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 4:
            continue

        href = a.get("href", "")
        if href.startswith("http"):
            link_url = href
        elif href.startswith("/"):
            link_url = urljoin(url, href)
        else:
            continue

        # Match keyword against link text + parent container text
        container = a.parent or a
        container_text = container.get_text(" ", strip=True)
        searchable = (title + " " + container_text).lower()

        if not any(kw in searchable for kw in kw_lower):
            continue

        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Extract price from container
        price = ""
        price_match = _PRICE_RE.search(container_text)
        if price_match:
            price = price_match.group().strip()

        # Extract image from container
        image_url = ""
        img = container.find("img")
        if img:
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or ""
            )
            if src.startswith("http"):
                image_url = src
            elif src.startswith("/"):
                image_url = urljoin(url, src)

        results.append(GenericResult(
            site_name=domain,
            site_url=url,
            title=title,
            url=link_url,
            price=price,
            image_url=image_url,
        ))

    logger.info("Scraped %s — %d keyword matches found", url, len(results))
    return results


def validate_url(url: str) -> tuple[bool, str]:
    """Check URL is valid and reachable. Returns (ok, error_message)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "URL must start with http:// or https://"
    if not parsed.netloc:
        return False, "Invalid URL — no domain found"
    try:
        session = requests.Session()
        session.headers.update(_HEADERS)
        resp = session.head(url, timeout=10, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return False, f"Could not reach that URL: {exc}"
    return True, ""
