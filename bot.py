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
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "your_manager").lstrip("@")
OWNER_USER_ID = int(os.environ["OWNER_USER_ID"])
PORT = int(os.environ.get("PORT", "0"))

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


PROFILE_LABELS = {
    "company": ("С кем едет", {"solo": "одна/один", "pair": "с парой", "family": "семья с детьми", "friends": "с компанией"}),
    "when": ("Когда", {"soon": "ближайший месяц", "1-3": "через 1-3 мес", "3-6": "через 3-6 мес", "later": "заранее"}),
    "budget": ("Бюджет/чел", {"lo": "до 150к ₽", "mid": "150-300к ₽", "hi": "300-500к ₽", "lux": "от 500к ₽"}),
    "direction": ("Направление", {"med": "Средиземка", "north": "Северная Европа", "east": "Восток (Дубай/Азия)", "carib": "Карибы/Америка", "any": "не важно"}),
    "first": ("Опыт", {"yes": "первый круиз", "no": "уже ходил(а)"}),
    "visa": ("Виза", {"schengen": "есть Шенген", "other": "есть другая", "none": "нет визы", "ready": "готова оформить"}),
}
AVOID_LABELS = {"seasick": "качка", "longflight": "долгий перелёт", "transfers": "пересадки", "visa": "визы"}


def format_profile(profile: dict) -> str:
    lines = []
    for key, (label, mapping) in PROFILE_LABELS.items():
        val = profile.get(key)
        if val:
            lines.append(f"• {label}: {mapping.get(val, val)}")
    avoid = profile.get("avoid") or []
    if avoid:
        lines.append("• Избегает: " + ", ".join(AVOID_LABELS.get(a, a) for a in avoid))
    return "\n".join(lines) if lines else "— (не указан)"


@dp.message(F.web_app_data)
async def on_webapp_data(message: Message) -> None:
    raw = message.web_app_data.data or ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"type": "manual_lead", "raw": raw}

    lead_type = payload.get("type", "manual_lead")
    cruise = payload.get("cruise") or {}
    profile = payload.get("profile") or {}

    user = message.from_user
    user_tag = f"@{user.username}" if user.username else f"id{user.id}"
    user_name = user.full_name or user_tag

    # Notify owner (Настя)
    owner_lines = ["🔥 <b>Новая заявка через квиз</b>", ""]
    if lead_type == "cruise_lead" and cruise:
        owner_lines += [
            f"🚢 <b>{cruise.get('title', '—')}</b>",
            f"📅 {cruise.get('date', '—')} · {cruise.get('nights', '?')} ночей · {cruise.get('vendor', '')}",
            f"🔖 {cruise.get('num', '')}",
        ]
    else:
        owner_lines.append("🤔 <i>Виджет ничего не нашёл — просит подобрать вручную</i>")
    owner_lines += ["", "<b>Профиль клиента:</b>", format_profile(profile), "", f"👤 {user_name} ({user_tag})"]

    try:
        await bot.send_message(OWNER_USER_ID, "\n".join(owner_lines), parse_mode="HTML")
    except Exception as exc:
        logging.exception("Failed to notify owner: %s", exc)

    # Confirm to user
    if lead_type == "cruise_lead" and cruise:
        text = (
            f"Отлично! 🚢\n\n"
            f"Заявка на «{cruise.get('title', 'круиз')}» ушла Насте. "
            f"Она свяжется с вами в течение дня — покажет актуальные каюты и цены, оформит бронирование.\n\n"
            f"Если хотите, можете сразу написать ей: @{MANAGER_USERNAME}"
        )
    else:
        text = (
            f"Спасибо! 🙌\n\n"
            f"Настя увидит вашу заявку и подберёт круиз вручную — напишет в течение дня. "
            f"Или напишите ей сами: @{MANAGER_USERNAME}"
        )

    await message.answer(text, reply_markup=manager_kb())


async def healthcheck(_request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def run_http_server(port: int) -> None:
    app = web.Application()
    app.router.add_get("/", healthcheck)
    app.router.add_get("/health", healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("HTTP healthcheck listening on 0.0.0.0:%s", port)
    while True:
        await asyncio.sleep(3600)


async def main() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    tasks = [asyncio.create_task(dp.start_polling(bot))]
    if PORT:
        tasks.append(asyncio.create_task(run_http_server(PORT)))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
