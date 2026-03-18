"""Бот портфеля «Электронный Мир»: ввод бренда / группы / направления → почта."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from translit import has_cyrillic, lat_to_cyr, query_variants

BOT_VERSION = "1.3.4"
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
TELEGRAM_PROXY = (os.getenv("TELEGRAM_PROXY") or "").strip() or None

WELCOME = (
    'Портфель <b>ЭлМир "Проектные решения"</b>\n'
    "Напишите бренд, группу или направление — ответом будет почта.\n"
    "Все бренды списком: /brands"
)

if not BOT_TOKEN:
    raise SystemExit("Укажите bot_token в конфигурации дополнения.")

DIR = Path(__file__).resolve().parent
VENDORS_PATH = DIR / "vendors.json"
ALIASES_PATH = DIR / "brand_aliases.json"


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^\w\sа-яё\-&+]", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def load_vendors() -> list[dict]:
    with open(VENDORS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_aliases() -> dict[str, list[str]]:
    if not ALIASES_PATH.is_file():
        return {}
    with open(ALIASES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _brand_search_forms(brand: str, aliases_map: dict[str, list[str]]) -> set[str]:
    """Все варианты написания бренда для поиска: норма, алиасы, транслит."""
    forms = set()
    b = _norm(brand)
    if b:
        forms.add(b)
    for alias in aliases_map.get(brand, []):
        a = _norm(alias)
        if a and len(a) >= 2:
            forms.add(a)
    if b and not has_cyrillic(b):
        cyr = lat_to_cyr(b)
        if cyr and len(cyr) >= 2:
            forms.add(_norm(cyr))
    return forms


def _brand_match(brand: str, query_variants_list: list[str], brand_forms: set[str]) -> bool:
    if not brand_forms or not query_variants_list:
        return False
    for qv in query_variants_list:
        if len(qv) < 2:
            continue
        for bf in brand_forms:
            if qv == bf or qv in bf or bf in qv:
                return True
    return False


def _compact(s: str) -> str:
    return _norm(s).replace("-", "").replace(" ", "")


def _text_match(field: str, q: str) -> bool:
    t = _norm(field)
    if not t:
        return False
    if t == q or q in t or t in q:
        return True
    tc, qc = _compact(field), _compact(q)
    return len(qc) >= 2 and (qc in tc or tc in qc)


def search(query: str, vendors: list[dict], aliases_map: dict[str, list[str]]) -> list[dict]:
    q_norm = _norm(query)
    if len(q_norm) < 2:
        return []
    q_variants = [q_norm] + [v for v in query_variants(query) if v != q_norm]
    q_variants = list(dict.fromkeys(x for x in q_variants if x and len(x) >= 2))

    by_brand: list[dict] = []
    for v in vendors:
        brand = v.get("brand") or ""
        forms = _brand_search_forms(brand, aliases_map)
        if _brand_match(brand, q_variants, forms):
            by_brand.append(v)
    if by_brand:
        return by_brand

    by_group = [v for v in vendors if v.get("group") and _text_match(v["group"], q_norm)]
    if by_group:
        return by_group

    by_dir = [v for v in vendors if v.get("direction") and _text_match(v["direction"], q_norm)]
    return by_dir


def emails_from_hits(hits: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in hits:
        em = (v.get("email") or "").strip()
        if em and em not in seen:
            seen.add(em)
            out.append(em)
    return out


def format_reply(hits: list[dict]) -> str:
    emails = emails_from_hits(hits)
    if not emails:
        return ""
    if len(emails) == 1:
        return emails[0]
    return "\n".join(emails)


def get_all_brands_sorted(vendors: list[dict]) -> list[str]:
    """Уникальные бренды: сначала русские по алфавиту, потом английские по алфавиту."""
    unique: set[str] = set()
    for v in vendors:
        b = (v.get("brand") or "").strip()
        if b:
            unique.add(b)
    ru = sorted([b for b in unique if has_cyrillic(b)])
    en = sorted([b for b in unique if not has_cyrillic(b)], key=str.lower)
    return ru + en


def build_clarify_options(hits: list[dict]) -> list[tuple[str, str]]:
    """Уникальные варианты (подпись для кнопки, почта) по направлениям/группам."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for v in hits:
        direction = (v.get("direction") or "").strip()
        group = (v.get("group") or "").strip()
        email = (v.get("email") or "").strip()
        if not email:
            continue
        # Подпись: группа, если есть, иначе направление
        label = group if group and group != "—" else direction
        if not label:
            label = email
        key = (label, email)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    vendors = load_vendors()
    aliases_map = load_aliases()
    logging.info("Каталог: %s брендов, алиасов: %s", len(vendors), len(aliases_map))

    # Ожидание выбора: user_id -> (brand_name, [(label, email), ...])
    user_clarify: dict[int, tuple[str, list[tuple[str, str]]]] = {}

    if TELEGRAM_PROXY:
        bot = Bot(token=BOT_TOKEN, session=AiohttpSession(proxy=TELEGRAM_PROXY))
    else:
        bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        user_clarify.pop(user_id, None)
        await message.answer(WELCOME, parse_mode="HTML")

    @dp.message(Command("brands"))
    async def cmd_brands(message: types.Message) -> None:
        brands = get_all_brands_sorted(vendors)
        if not brands:
            await message.answer("Список брендов пуст.")
            return
        header = 'Все бренды портфеля ЭлМир "Проектные решения"\n\n'
        body = "\n".join(brands)
        text = header + body
        if len(text) <= 4096:
            await message.answer(text)
            return
        await message.answer(header.strip())
        max_len = 4000
        chunk: list[str] = []
        size = 0
        for b in brands:
            if size + len(b) + 1 > max_len and chunk:
                await message.answer("\n".join(chunk))
                chunk = []
                size = 0
            chunk.append(b)
            size += len(b) + 1
        if chunk:
            await message.answer("\n".join(chunk))

    def _make_clarify_kb(options: list[tuple[str, str]]) -> InlineKeyboardMarkup:
        row_size = 2 if len(options) > 4 else 1
        rows = []
        for i, (label, _) in enumerate(options):
            btn = InlineKeyboardButton(text=label[:64], callback_data=f"cl|{i}")
            if rows and len(rows[-1]) < row_size:
                rows[-1].append(btn)
            else:
                rows.append([btn])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @dp.callback_query(F.data.startswith("cl|"))
    async def on_clarify_callback(callback: types.CallbackQuery) -> None:
        user_id = callback.from_user.id if callback.from_user else 0
        state = user_clarify.get(user_id)
        if not state:
            await callback.answer("Введите бренд заново.", show_alert=True)
            await callback.answer()
            return
        brand_name, options = state
        payload = callback.data.split("|", 1)[1]
        try:
            if payload == "back":
                # Назад — в том же сообщении снова показать список направлений
                kb = _make_clarify_kb(options)
                await callback.message.edit_text(
                    f"<b>{brand_name}</b> есть в нескольких направлениях. Уточните, что нужно:",
                    reply_markup=kb,
                    parse_mode="HTML",
                )
                await callback.answer()
                return
            idx = int(payload)
            if 0 <= idx < len(options):
                label, email = options[idx]
                kb_back = InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="◀ Назад", callback_data="cl|back")
                    ]]
                )
                await callback.message.edit_text(email, reply_markup=kb_back)
            else:
                await callback.answer("Неверный выбор.", show_alert=True)
        except ValueError:
            await callback.answer("Ошибка.", show_alert=True)
        await callback.answer()

    @dp.message(F.text)
    async def on_text(message: types.Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        text = (message.text or "").strip()
        if text.startswith("/"):
            return

        # Если ждём уточнение — проверяем, не выбрал ли пользователь текстом (например "Ноутбуки")
        if user_id in user_clarify:
            _, options = user_clarify[user_id]
            q_norm = _norm(text)
            for i, (label, email) in enumerate(options):
                if q_norm == _norm(label) or q_norm in _norm(label) or _norm(label) in q_norm:
                    await message.answer(email)
                    user_clarify.pop(user_id, None)
                    return
            # не совпало — сбрасываем уточнение и ищем как обычно
            user_clarify.pop(user_id, None)

        hits = search(text, vendors, aliases_map)
        if not hits:
            await message.answer(
                "Не нашёл. Попробуйте другое написание (рус/англ, с опечаткой).\n\n" + WELCOME,
                parse_mode="HTML",
            )
            return

        options = build_clarify_options(hits)
        if len(options) == 1:
            await message.answer(options[0][1])
            return
        if len(options) > 1:
            brand_name = hits[0].get("brand") or "Бренд"
            user_clarify[user_id] = (brand_name, options)
            kb = _make_clarify_kb(options)
            await message.answer(
                f"<b>{brand_name}</b> есть в нескольких направлениях. Уточните, что нужно:",
                reply_markup=kb,
                parse_mode="HTML",
            )
            return

        reply = format_reply(hits)
        if reply:
            await message.answer(reply)

    await asyncio.sleep(20)
    while True:
        try:
            await dp.start_polling(bot)
        except TelegramNetworkError as e:
            logging.warning("Telegram, пауза 60 с: %s", e)
            await asyncio.sleep(60)
        except (OSError, ConnectionError, asyncio.TimeoutError) as e:
            logging.warning("Сеть, пауза 60 с: %s", e)
            await asyncio.sleep(60)
        except Exception as e:
            logging.exception("polling: %s", e)
            await asyncio.sleep(60)
        else:
            break


if __name__ == "__main__":
    asyncio.run(main())
