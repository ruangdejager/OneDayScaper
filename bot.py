import asyncio
import datetime
import logging
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import config
import database
from generic_scraper import validate_url
from notifier import send_daily_notifications

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "<b>OneDayOnly Deal Alerts</b>\n\n"
    "I scrape websites every morning at 4am and notify you when your keywords appear.\n\n"
    "<b>Keyword commands:</b>\n"
    "/subscribe &lt;keyword&gt; — Add a keyword alert\n"
    "/unsubscribe — Remove a keyword alert\n"
    "/list — View your subscribed keywords\n\n"
    "<b>Website commands:</b>\n"
    "/addsite &lt;url&gt; — Add a website to scrape\n"
    "/mysites — View your added websites\n"
    "/removesites — Remove a website\n\n"
    "<i>Keywords match against all your added sites + OneDayOnly.</i>"
)


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔔 My Keywords", callback_data="show_keywords"),
            InlineKeyboardButton("🌐 My Sites", callback_data="show_sites"),
        ],
        [
            InlineKeyboardButton("➕ Subscribe", callback_data="prompt_subscribe"),
            InlineKeyboardButton("➕ Add Site", callback_data="prompt_addsite"),
        ],
        [InlineKeyboardButton("❓ Help", callback_data="show_help")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Welcome to <b>OneDayOnly Deal Alerts</b>!\n\n"
        "Subscribe to keywords and I'll notify you every morning at 4am when matching deals go live.",
        parse_mode=ParseMode.HTML,
        reply_markup=_main_keyboard(),
    )


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyword = " ".join(context.args).strip() if context.args else ""
    if not keyword:
        await update.message.reply_text(
            "Please provide a keyword.\nExample: <code>/subscribe coffee</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    user = update.effective_user
    inserted = database.add_subscription(
        config.DATABASE_PATH, user.id, user.username or user.first_name, keyword
    )
    if inserted:
        await update.message.reply_text(
            f"Subscribed to <b>{keyword}</b>. I'll alert you when it appears on OneDayOnly!",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"You're already subscribed to <b>{keyword}</b>.",
            parse_mode=ParseMode.HTML,
        )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keywords = database.get_user_keywords(config.DATABASE_PATH, user.id)

    if not keywords:
        await update.message.reply_text("You have no subscriptions to remove.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Remove: {kw}", callback_data=f"unsub:{kw}")]
        for kw in keywords
    ])
    await update.message.reply_text(
        "Tap a keyword to remove it:",
        reply_markup=keyboard,
    )


async def list_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keywords = database.get_user_keywords(config.DATABASE_PATH, user.id)

    if not keywords:
        await update.message.reply_text(
            "You have no active subscriptions.\nUse /subscribe &lt;keyword&gt; to add one.",
            parse_mode=ParseMode.HTML,
        )
        return

    bullet_list = "\n".join(f"• {kw}" for kw in keywords)
    await update.message.reply_text(
        f"<b>Your subscribed keywords:</b>\n{bullet_list}",
        parse_mode=ParseMode.HTML,
    )


async def addsite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = " ".join(context.args).strip() if context.args else ""
    if not url:
        await update.message.reply_text(
            "Please provide a URL.\nExample: <code>/addsite https://www.takealot.com</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    await update.message.reply_text("⏳ Checking that URL, one moment...")

    ok, error = await asyncio.get_event_loop().run_in_executor(None, validate_url, url)
    if not ok:
        await update.message.reply_text(f"❌ {error}")
        return

    from urllib.parse import urlparse
    name = urlparse(url).netloc.replace("www.", "")
    user = update.effective_user
    inserted = database.add_user_site(config.DATABASE_PATH, user.id, url, name)
    if inserted:
        await update.message.reply_text(
            f"✅ Added <b>{name}</b> to your scrape list.\n"
            f"Your keywords will be matched against this site every morning.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(f"You've already added <b>{name}</b>.", parse_mode=ParseMode.HTML)


async def mysites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    sites = database.get_user_sites(config.DATABASE_PATH, user.id)
    if not sites:
        await update.message.reply_text(
            "You have no custom sites yet.\nUse /addsite &lt;url&gt; to add one.",
            parse_mode=ParseMode.HTML,
        )
        return
    lines = "\n".join(f"• <a href='{s['url']}'>{s['name']}</a>" for s in sites)
    await update.message.reply_text(
        f"<b>Your sites</b> (+ OneDayOnly always included):\n{lines}",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def removesites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    sites = database.get_user_sites(config.DATABASE_PATH, user.id)
    if not sites:
        await update.message.reply_text("You have no custom sites to remove.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Remove: {s['name']}", callback_data=f"rmsite:{s['url']}")]
        for s in sites
    ])
    await update.message.reply_text("Tap a site to remove it:", reply_markup=keyboard)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    user = update.effective_user

    if data == "prompt_subscribe":
        await query.edit_message_text(
            "Send me a keyword to subscribe to:\n\n"
            "<code>/subscribe &lt;keyword&gt;</code>\n\n"
            "Example: <code>/subscribe lego</code>",
            parse_mode=ParseMode.HTML,
        )

    elif data == "show_keywords":
        keywords = database.get_user_keywords(config.DATABASE_PATH, user.id)
        if keywords:
            bullet_list = "\n".join(f"• {kw}" for kw in keywords)
            text = f"<b>Your subscribed keywords:</b>\n{bullet_list}"
        else:
            text = "You have no active subscriptions yet.\nUse /subscribe &lt;keyword&gt; to add one."
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    elif data == "show_help":
        await query.edit_message_text(HELP_TEXT, parse_mode=ParseMode.HTML)

    elif data == "prompt_addsite":
        await query.edit_message_text(
            "Send me a website URL to add:\n\n"
            "<code>/addsite &lt;url&gt;</code>\n\n"
            "Example: <code>/addsite https://www.takealot.com</code>",
            parse_mode=ParseMode.HTML,
        )

    elif data == "show_sites":
        sites = database.get_user_sites(config.DATABASE_PATH, user.id)
        if sites:
            lines = "\n".join(f"• <a href='{s['url']}'>{s['name']}</a>" for s in sites)
            text = f"<b>Your sites</b> (+ OneDayOnly always included):\n{lines}"
        else:
            text = "You have no custom sites yet.\nUse /addsite &lt;url&gt; to add one."
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    elif data.startswith("unsub:"):
        keyword = data[len("unsub:"):]
        removed = database.remove_subscription(config.DATABASE_PATH, user.id, keyword)
        if removed:
            await query.edit_message_text(
                f"Removed <b>{keyword}</b> from your subscriptions.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await query.edit_message_text(
                f"Could not find <b>{keyword}</b> in your subscriptions.",
                parse_mode=ParseMode.HTML,
            )

    elif data.startswith("rmsite:"):
        url = data[len("rmsite:"):]
        removed = database.remove_user_site(config.DATABASE_PATH, user.id, url)
        from urllib.parse import urlparse
        name = urlparse(url).netloc.replace("www.", "")
        if removed:
            await query.edit_message_text(f"Removed <b>{name}</b> from your sites.", parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(f"Could not find <b>{name}</b> in your sites.", parse_mode=ParseMode.HTML)


def main() -> None:
    database.init_db(config.DATABASE_PATH)

    application = Application.builder().token(config.BOT_TOKEN).build()

    assert application.job_queue is not None, (
        "JobQueue is not available. Install with: pip install 'python-telegram-bot[job-queue]'"
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    application.add_handler(CommandHandler("list", list_keywords))
    application.add_handler(CommandHandler("addsite", addsite))
    application.add_handler(CommandHandler("mysites", mysites))
    application.add_handler(CommandHandler("removesites", removesites))
    application.add_handler(CallbackQueryHandler(button_callback))

    job_time = datetime.time(
        hour=config.SCRAPE_HOUR,
        minute=config.SCRAPE_MINUTE,
        tzinfo=ZoneInfo("Africa/Johannesburg"),
    )
    application.job_queue.run_daily(
        callback=send_daily_notifications,
        time=job_time,
        name="daily_scrape",
    )

    logger.info(
        "Bot started. Daily scrape scheduled at %02d:%02d SAST.",
        config.SCRAPE_HOUR,
        config.SCRAPE_MINUTE,
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    main()
