import asyncio
import logging

from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import CallbackContext

import config
from database import get_all_subscriptions, get_all_user_sites
from generic_scraper import GenericResult, scrape_site
from scraper import Product, scrape_products

logger = logging.getLogger(__name__)


def match_products(
    products: list[Product],
    subscriptions: dict[int, dict],
) -> dict[int, list[Product]]:
    matches: dict[int, list[Product]] = {}
    for user_id, info in subscriptions.items():
        user_matches = [
            p for p in products
            if any(kw in f"{p.title} {p.brand}".lower() for kw in info["keywords"])
        ]
        if user_matches:
            matches[user_id] = user_matches
    return matches


def format_product_message(product: Product) -> str:
    brand_part = f"<b>{product.brand}</b> — " if product.brand else ""
    return (
        f"{brand_part}{product.title}\n"
        f"Price: {product.price}\n"
        f'<a href="{product.url}">View Deal</a>'
    )


def format_generic_message(result: GenericResult) -> str:
    price_part = f"\nPrice: {result.price}" if result.price else ""
    return (
        f"<b>{result.site_name}</b>\n"
        f"{result.title}{price_part}\n"
        f'<a href="{result.url}">View</a>'
    )


async def _send_item(context: CallbackContext, user_id: int, text: str, image_url: str) -> None:
    if image_url:
        try:
            await context.bot.send_photo(
                chat_id=user_id, photo=image_url, caption=text, parse_mode=ParseMode.HTML
            )
            return
        except TelegramError:
            pass
    await context.bot.send_message(
        chat_id=user_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=False
    )


async def send_daily_notifications(context: CallbackContext) -> None:
    logger.info("Daily scrape starting...")

    try:
        odo_products = await asyncio.to_thread(scrape_products)
    except Exception as exc:
        logger.error("OneDayOnly scrape failed: %s", exc)
        odo_products = []

    subscriptions = await asyncio.to_thread(get_all_subscriptions, config.DATABASE_PATH)
    all_user_sites = await asyncio.to_thread(get_all_user_sites, config.DATABASE_PATH)

    if not subscriptions:
        logger.info("No subscribers — nothing to notify.")
        return

    odo_matches = match_products(odo_products, subscriptions)

    # Scrape custom sites, cached by url+keywords to avoid duplicate fetches
    site_cache: dict[str, list[GenericResult]] = {}
    site_matches: dict[int, list[GenericResult]] = {}

    for user_id, sites in all_user_sites.items():
        if user_id not in subscriptions:
            continue
        keywords = subscriptions[user_id]["keywords"]
        user_results: list[GenericResult] = []
        for site in sites:
            cache_key = f"{site['url']}|{'|'.join(sorted(keywords))}"
            if cache_key not in site_cache:
                site_cache[cache_key] = await asyncio.to_thread(scrape_site, site["url"], keywords)
            user_results.extend(site_cache[cache_key])
        if user_results:
            site_matches[user_id] = user_results

    notified = 0
    for user_id, info in subscriptions.items():
        matched_products = odo_matches.get(user_id, [])
        matched_sites = site_matches.get(user_id, [])
        total = len(matched_products) + len(matched_sites)

        try:
            if total > 0:
                sources = ["OneDayOnly"] if matched_products else []
                for r in matched_sites:
                    if r.site_name not in sources:
                        sources.append(r.site_name)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🛍️ Good morning! Found <b>{total} deal{'s' if total != 1 else ''}</b> "
                        f"across <b>{' & '.join(sources)}</b> matching your keywords today:"
                    ),
                    parse_mode=ParseMode.HTML,
                )
                for product in matched_products:
                    await asyncio.sleep(0.1)
                    await _send_item(context, user_id, format_product_message(product), product.image_url)
                for result in matched_sites:
                    await asyncio.sleep(0.1)
                    await _send_item(context, user_id, format_generic_message(result), result.image_url)
            else:
                kw_list = ", ".join(f"<i>{k}</i>" for k in info["keywords"])
                site_count = len(all_user_sites.get(user_id, []))
                sources_str = (
                    f"OneDayOnly + {site_count} custom site{'s' if site_count != 1 else ''}"
                    if site_count else "OneDayOnly"
                )
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"☀️ Good morning! Scraped <b>{sources_str}</b> — no matches today for {kw_list}.",
                    parse_mode=ParseMode.HTML,
                )
            notified += 1
        except Forbidden:
            logger.warning("User %s has blocked the bot — skipping.", user_id)
        except TelegramError as exc:
            logger.error("Failed to notify user %s: %s", user_id, exc)

    logger.info("Daily notifications complete — notified %d user(s).", notified)
