import logging
import os

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("crypto-bot")

TOKEN = os.environ["BOT_TOKEN"]
API = "https://api.coingecko.com/api/v3"

COINS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binancecoin": "BNB",
    "ripple": "XRP",
    "dogecoin": "DOGE",
}


async def cg(path: str, params: dict | None = None) -> dict | list:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{API}{path}", params=params)
        r.raise_for_status()
        return r.json()


def fmt_price(p: float) -> str:
    return f"${p:,.2f}" if p >= 1 else f"${p:,.6f}"


def main_menu() -> InlineKeyboardMarkup:
    rows, row = [], []
    for cid, sym in COINS.items():
        row.append(InlineKeyboardButton(sym, callback_data=f"price:{cid}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton("🏆 Top 10", callback_data="top"),
            InlineKeyboardButton("🔥 Trending", callback_data="trending"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data="menu")]])


async def price_text(coin_id: str) -> str:
    data = await cg(
        "/simple/price",
        {"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true"},
    )
    if coin_id not in data:
        return "Coin not found."
    d = data[coin_id]
    change = d.get("usd_24h_change") or 0
    arrow = "🟢" if change >= 0 else "🔴"
    return f"*{coin_id.title()}*\nPrice: {fmt_price(d['usd'])}\n24h: {arrow} {change:+.2f}%"


async def top_text() -> str:
    data = await cg(
        "/coins/markets",
        {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 10, "page": 1},
    )
    lines = ["*Top 10 by market cap*\n"]
    for i, c in enumerate(data, 1):
        ch = c.get("price_change_percentage_24h") or 0
        lines.append(f"{i}. {c['symbol'].upper()} — {fmt_price(c['current_price'])} ({ch:+.2f}%)")
    return "\n".join(lines)


async def trending_text() -> str:
    data = await cg("/search/trending")
    lines = ["*Trending coins*\n"]
    for i, item in enumerate(data["coins"][:7], 1):
        c = item["item"]
        lines.append(f"{i}. {c['name']} ({c['symbol']})")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Crypto bot. Pick an option or use /price <coin>, e.g. /price bitcoin",
        reply_markup=main_menu(),
    )


async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /price bitcoin")
        return
    query = context.args[0].lower()
    try:
        # Resolve symbol or name to a CoinGecko id
        res = await cg("/search", {"query": query})
        coins = res.get("coins", [])
        if not coins:
            await update.message.reply_text("Coin not found.")
            return
        text = await price_text(coins[0]["id"])
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        log.exception("price command failed")
        await update.message.reply_text("API error, try again in a moment.")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        if q.data == "menu":
            await q.edit_message_text("Choose an option:", reply_markup=main_menu())
        elif q.data == "top":
            await q.edit_message_text(await top_text(), parse_mode="Markdown", reply_markup=back_menu())
        elif q.data == "trending":
            await q.edit_message_text(await trending_text(), parse_mode="Markdown", reply_markup=back_menu())
        elif q.data.startswith("price:"):
            text = await price_text(q.data.split(":", 1)[1])
            await q.edit_message_text(text, parse_mode="Markdown", reply_markup=back_menu())
    except Exception:
        log.exception("button handler failed")
        await q.edit_message_text("API error (rate limit?). Try again shortly.", reply_markup=back_menu())


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler(["start", "menu"], start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    log.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
