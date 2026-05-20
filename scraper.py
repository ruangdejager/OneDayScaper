import logging
import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-ZA,en;q=0.9",
}

_PRICE_RE = re.compile(r"R[\d,]+")


@dataclass
class Product:
    title: str
    brand: str
    price: str
    url: str
    image_url: str = field(default="")


def scrape_products() -> list[Product]:
    session = requests.Session()
    session.headers.update(_HEADERS)

    try:
        resp = session.get(config.BASE_URL, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch onedayonly.co.za: %s", exc)
        raise

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.select('a[href*="/products/"]')

    products: list[Product] = []
    seen_urls: set[str] = set()

    for card in cards:
        product = _parse_product_card(card)
        if product and product.url not in seen_urls:
            products.append(product)
            seen_urls.add(product.url)

    if len(products) < 5:
        logger.warning(
            "Only %d products found — onedayonly.co.za HTML structure may have changed.",
            len(products),
        )
    else:
        logger.info("Scraped %d products from onedayonly.co.za", len(products))

    return products


def _parse_product_card(tag) -> Product | None:
    try:
        href = tag.get("href", "")
        if not href:
            return None

        url = config.BASE_URL + href if href.startswith("/") else href

        title_attr = tag.get("title", "").strip()
        if not title_attr:
            return None

        if "," in title_attr:
            brand, _, title = title_attr.partition(",")
            brand = brand.strip()
            title = title.strip()
        else:
            brand = ""
            title = title_attr

        price = _extract_price(tag)

        img_tag = tag.find("img")
        image_url = img_tag.get("src", "") if img_tag else ""

        return Product(title=title, brand=brand, price=price, url=url, image_url=image_url)
    except Exception as exc:
        logger.debug("Skipping malformed product card: %s", exc)
        return None


def _extract_price(tag) -> str:
    for text in tag.stripped_strings:
        if _PRICE_RE.match(text):
            return text
    return "N/A"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    products = scrape_products()
    for p in products[:10]:
        print(f"[{p.brand}] {p.title} — {p.price}")
        print(f"  {p.url}")
