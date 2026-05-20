import asyncio
import logging

from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import CallbackContext

import config
from database import get_all_subscriptions
from scraper import Product, scrape_products

logger = logging.getLogger(__name__)


def match_products(
    products: list[Product],
    subscriptions: dict[int, dict],
) -> dict[int, list[Product]]:
    matches: dict[int, list[Product]] = {}
    for user_id, info in subscriptions.items():
        user_matches = []
        for product in products:
            searchable = f"{product.title} {product.brand}".lower()
            if any(kw in searchable for kw in info["keywords"]):
                user_matches.append(product)
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


async def send_daily_notifications(context: CallbackContext) -> None:
    logger.info("Daily scrape starting...")

    try:
        products = await asyncio.to_thread(scrape_products)
    except Exception as exc:
        logger.error("Scrape failed, skipping notifications: %s", exc)
        return

    subscriptions = await asyncio.to_thread(get_all_subscriptions, config.DATABASE_PATH)

    if not subscriptions:
        logger.info("No subscribers — nothing to notify.")
        return

    matches = match_products(products, subscriptions)

    if not matches:
        logger.info("Daily scrape complete — 0 users matched today.")
        return

    notified = 0
    for user_id in subscriptions:
        matched_products = matches.get(user_id, [])
        try:
            if matched_products:
                count = len(matched_products)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🛍️ Good morning! Found <b>{count} deal{'s' if count != 1 else ''}</b> matching your keywords today:",
                    parse_mode=ParseMode.HTML,
                )
                for product in matched_products:
                    await asyncio.sleep(0.1)
                    msg = format_product_message(product)
                    if product.image_url:
                        try:
                            await context.bot.send_photo(
                                chat_id=user_id,
                                photo=product.image_url,
                                caption=msg,
                                parse_mode=ParseMode.HTML,
                            )
                            continue
                        except TelegramError:
                            pass
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=msg,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False,
                    )
            else:
                keywords = subscriptions[user_id]["keywords"]
                kw_list = ", ".join(f"<i>{k}</i>" for k in keywords)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"☀️ Good morning! OneDayOnly has been scraped — no matches today for {kw_list}.",
                    parse_mode=ParseMode.HTML,
                )
            notified += 1
        except Forbidden:
            logger.warning("User %s has blocked the bot — skipping.", user_id)
        except TelegramError as exc:
            logger.error("Failed to notify user %s: %s", user_id, exc)

    logger.info("Daily notifications complete — notified %d user(s).", notified)
