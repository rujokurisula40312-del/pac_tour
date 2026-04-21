import asyncio
import json
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "your_manager").lstrip("@")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def search_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔎 Поиск круизов",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ]
    )


def manager_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉️ Написать менеджеру",
                    url=f"https://t.me/{MANAGER_USERNAME}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔎 Новый поиск",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ],
        ]
    )


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(
        "Привет! 👋\n\n"
        "Я помогу подобрать круиз. Нажмите кнопку ниже, чтобы открыть поиск — "
        "выбирайте направление, даты и удобные опции.",
        reply_markup=search_kb(),
    )


@dp.message(F.web_app_data)
async def on_webapp_data(message: Message) -> None:
    raw = message.web_app_data.data or ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"action": "contact_manager", "raw": raw}

    details = payload.get("details") or {}
    summary_lines = []
    for key in ("vendor", "destination", "departure", "dates", "price"):
        value = details.get(key)
        if value:
            summary_lines.append(f"• {key}: {value}")
    summary = "\n".join(summary_lines)

    text = "Отлично! 🚢\n"
    if summary:
        text += f"\nВаш выбор:\n{summary}\n"
    text += (
        f"\nЧтобы забронировать или уточнить детали — напишите нашему менеджеру "
        f"@{MANAGER_USERNAME}."
    )

    await message.answer(text, reply_markup=manager_kb())


async def main() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
