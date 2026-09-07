import asyncio
import html
import json
import logging
import os
from collections import defaultdict
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiohttp import web
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "your_manager").lstrip("@")
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
AI_MODEL = os.getenv("AI_MODEL", "claude-haiku-4-5")
PORT = int(os.environ.get("PORT", "0"))


def _parse_ids(raw: str) -> list[int]:
    out: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            logging.warning("Skipping non-integer chat id: %r", part)
    return out


MANAGERS_CHAT_IDS: list[int] = _parse_ids(os.getenv("MANAGERS_CHAT_IDS", ""))
if not MANAGERS_CHAT_IDS:
    MANAGERS_CHAT_IDS = _parse_ids(os.getenv("OWNER_USER_ID", ""))

MAX_HISTORY = 20

logging.basicConfig(level=logging.INFO)

if not MANAGERS_CHAT_IDS:
    logging.warning(
        "MANAGERS_CHAT_IDS not configured — leads will NOT be auto-forwarded. "
        "Set MANAGERS_CHAT_IDS or OWNER_USER_ID to a chat/group id.",
    )

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

histories: dict[int, list[dict[str, Any]]] = defaultdict(list)
forms: dict[int, dict[str, str]] = defaultdict(dict)
notified: dict[int, bool] = defaultdict(bool)


SYSTEM_PROMPT = """Ты — Зенди, дружелюбный AI-консьерж турагентства Pac Tour \
(специализация — морские круизы и туры). Отвечай только на русском.

Твоя работа:
1. Вести живой короткий диалог.
2. Постепенно, ненавязчиво выяснить у клиента:
   • направление (регион / страна / бассейн — Средиземноморье, Карибы, \
Северная Европа, Азия и т.д.);
   • примерные даты или месяц поездки;
   • желаемая длительность (в ночах);
   • бюджет (на человека или на всех);
   • количество и состав гостей (взрослых, детей с возрастом);
   • пожелания (тип отдыха: релакс / активный / семейный / премиум; \
тип каюты; питание; язык на борту и т.п.).
3. Как только собрано хотя бы 3–4 ключевых поля ИЛИ клиент просит связать \
с менеджером — вызови инструмент save_preferences и передай в него собранные \
поля (незаполненные оставляй пустой строкой). Можешь параллельно кратко \
ответить клиенту в тексте.
4. Никогда не выдумывай конкретные цены, названия лайнеров, точные даты \
рейсов или наличие мест. Точный подбор делает менеджер или поисковый WebApp — \
направляй туда.
5. Отвечай кратко (1–3 короткие фразы), задавай не больше 1–2 вопросов за раз.
6. Если клиент явно просит менеджера, готов бронировать, или разговор дошёл \
до цены/наличия — вежливо скажи, что сейчас передашь запрос менеджеру, и \
вызови save_preferences.
7. Не обещай скидок, гарантий, точных цен. Не спрашивай персональные данные \
(паспорт, номер карты и т.п.) — этим займётся менеджер.
8. Если клиент пишет не про туризм — коротко верни разговор к подбору поездки.

Стиль: тёплый, вежливый, на «вы», без канцелярита, с уместными эмодзи \
(🚢 🌴 ☀️ ✈️), но без спама эмодзи."""


SAVE_TOOL: dict[str, Any] = {
    "name": "save_preferences",
    "description": (
        "Сохранить собранные пожелания клиента по круизу/туру и подготовить "
        "передачу менеджеру. Вызывай, когда собрано хотя бы 3-4 поля из формы "
        "или когда клиент просит связаться с менеджером."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": "Направление / регион / страна",
            },
            "dates": {
                "type": "string",
                "description": "Даты, месяц или сезон поездки",
            },
            "duration": {
                "type": "string",
                "description": "Длительность, например '7 ночей'",
            },
            "budget": {
                "type": "string",
                "description": "Бюджет, например '2000 USD на человека'",
            },
            "guests": {
                "type": "string",
                "description": "Количество и состав гостей",
            },
            "preferences": {
                "type": "string",
                "description": "Тип отдыха, каюта, питание, прочие пожелания",
            },
            "notes": {
                "type": "string",
                "description": "Прочие важные детали, которые сказал клиент",
            },
        },
        "required": ["destination"],
    },
}


FIELD_LABELS = {
    "destination": "Направление",
    "dates": "Даты",
    "duration": "Длительность",
    "budget": "Бюджет",
    "guests": "Гости",
    "preferences": "Пожелания",
    "notes": "Прочее",
}


def action_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔎 Открыть поиск круизов",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✉️ Написать менеджеру",
                    url=f"https://t.me/{MANAGER_USERNAME}",
                )
            ],
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


def format_form(form: dict[str, str]) -> str:
    lines = []
    for key, label in FIELD_LABELS.items():
        value = (form.get(key) or "").strip()
        if value:
            lines.append(f"• {label}: {value}")
    return "\n".join(lines)


def _client_block(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "неизвестный клиент"
    parts: list[str] = []
    full_name = " ".join(p for p in (user.first_name, user.last_name) if p).strip()
    if full_name:
        parts.append(f"<b>{html.escape(full_name)}</b>")
    if user.username:
        parts.append(f"@{html.escape(user.username)}")
    parts.append(
        f'<a href="tg://user?id={user.id}">открыть чат</a> · '
        f"id <code>{user.id}</code>"
    )
    return "\n".join(parts)


async def notify_managers(message: Message, form: dict[str, str]) -> bool:
    """Post the collected lead to every configured manager destination.

    Returns True if at least one delivery succeeded. Marks the client as
    already-notified so subsequent saves are labelled as updates instead of
    new leads.
    """
    if not MANAGERS_CHAT_IDS:
        return False

    chat_id = message.chat.id
    is_update = notified[chat_id]
    header = "🔄 <b>Обновление заявки</b>" if is_update else "🆕 <b>Новая заявка</b>"
    summary = format_form(form) or "(поля пока пусты)"

    text = (
        f"{header}\n\n"
        f"👤 <b>Клиент</b>\n{_client_block(message)}\n\n"
        f"📋 <b>Пожелания</b>\n{html.escape(summary)}"
    )

    any_ok = False
    for manager_id in MANAGERS_CHAT_IDS:
        try:
            await bot.send_message(
                manager_id,
                text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            any_ok = True
        except Exception as exc:
            logging.warning("Notify manager %s failed: %s", manager_id, exc)

    if any_ok:
        notified[chat_id] = True
    return any_ok


async def ask_agent(
    chat_id: int, user_text: str
) -> tuple[str, dict[str, str] | None]:
    """Send user_text to Zendy. Returns (assistant_text, saved_form or None)."""
    history = histories[chat_id]
    history.append({"role": "user", "content": user_text})

    working_messages: list[dict[str, Any]] = list(history)
    saved_form: dict[str, str] | None = None
    text_chunks: list[str] = []

    for _ in range(2):
        response = await ai.messages.create(
            model=AI_MODEL,
            max_tokens=800,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[SAVE_TOOL],
            messages=working_messages,
        )

        tool_use_ids: list[str] = []
        for block in response.content:
            if block.type == "text":
                text_chunks.append(block.text)
            elif block.type == "tool_use" and block.name == "save_preferences":
                raw = dict(block.input or {})
                if saved_form is None:
                    saved_form = {}
                for k, v in raw.items():
                    if v:
                        saved_form[str(k)] = str(v)
                tool_use_ids.append(block.id)

        if response.stop_reason != "tool_use":
            break

        assistant_blocks = [b.model_dump() for b in response.content]
        working_messages.append({"role": "assistant", "content": assistant_blocks})
        working_messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tuid,
                        "content": "OK, saved.",
                    }
                    for tuid in tool_use_ids
                ],
            }
        )

    text = "\n\n".join(chunk for chunk in text_chunks if chunk).strip()

    history.append(
        {
            "role": "assistant",
            "content": text or "(записал ваши пожелания)",
        }
    )

    if len(history) > MAX_HISTORY:
        excess = len(history) - MAX_HISTORY
        if excess % 2:
            excess += 1
        del history[:excess]

    return text, saved_form


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    chat_id = message.chat.id
    histories[chat_id].clear()
    forms[chat_id].clear()
    notified[chat_id] = False
    await message.answer(
        "Привет! Я Зенди 🚢 — AI-консьерж Pac Tour.\n\n"
        "Расскажите пару слов о желаемом отдыхе — куда, когда, на сколько ночей "
        "и сколько человек — и я помогу подобрать направление. Точный поиск и "
        "бронирование делаем через WebApp или менеджера.\n\n"
        "С чего начнём? ✨",
        reply_markup=action_kb(),
    )


@dp.message(Command("reset"))
async def on_reset(message: Message) -> None:
    chat_id = message.chat.id
    histories[chat_id].clear()
    forms[chat_id].clear()
    notified[chat_id] = False
    await message.answer(
        "Диалог сброшен. Расскажите заново, какой отдых ищете 🌴",
        reply_markup=action_kb(),
    )


@dp.message(Command("chatid"))
async def on_chatid(message: Message) -> None:
    """Show current chat id and user id — for MANAGERS_CHAT_IDS setup."""
    user_id = message.from_user.id if message.from_user else "—"
    await message.answer(
        f"chat_id: <code>{message.chat.id}</code>\n"
        f"your user id: <code>{user_id}</code>\n\n"
        "Скопируйте нужный ID в переменную <code>MANAGERS_CHAT_IDS</code> "
        "в Render — сюда бот будет присылать заявки. Для группы: "
        "добавьте бота в группу и вызовите /chatid там (id будет отрицательным).",
        parse_mode=ParseMode.HTML,
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


@dp.message(F.text)
async def on_text(message: Message) -> None:
    chat_id = message.chat.id
    user_text = (message.text or "").strip()
    if not user_text:
        return

    try:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        pass

    try:
        reply, saved = await ask_agent(chat_id, user_text)
    except Exception:
        logging.exception("AI call failed for chat_id=%s", chat_id)
        await message.answer(
            "Кажется, у меня заминка 🛠 Попробуйте ещё раз — или напишите менеджеру.",
            reply_markup=action_kb(),
        )
        return

    if saved:
        for k, v in saved.items():
            if v:
                forms[chat_id][k] = v

    if not reply:
        reply = "Хорошо, записал ваши пожелания."

    if saved is not None:
        summary = format_form(forms[chat_id])
        if summary:
            reply += f"\n\n📋 Ваши пожелания:\n{summary}"

        was_update = notified[chat_id]
        delivered = await notify_managers(message, forms[chat_id])
        if delivered:
            if was_update:
                reply += (
                    "\n\n🔄 Обновление отправила менеджеру — он в курсе."
                )
            else:
                reply += (
                    "\n\n✅ Заявка ушла нашему менеджеру — он свяжется с вами "
                    "в ближайшее время. Пока можно уточнить детали в WebApp."
                )
        else:
            reply += (
                "\n\nМожете нажать «Написать менеджеру», чтобы он всё уточнил."
            )

    await message.answer(reply, reply_markup=action_kb())


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
