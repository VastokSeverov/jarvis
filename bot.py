import asyncio
import difflib
import logging
import re
from datetime import date, datetime, time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import brain
import config
import db
import reminders as rem

log = logging.getLogger("jarvis")
router = Router()
router.message.filter(F.from_user.id == config.OWNER_ID)  # everyone else is ignored

DEFAULT_OFFSETS = {"birthday": [1, 0], "deadline": [1, 0], "event": [1, 0], "task": [0]}
SHORTCUT = re.compile(r"^(done|delete|del)\s+#?(\d+)$", re.I)


def _date(value):
    try:
        return date.fromisoformat(value) if value else None
    except (ValueError, TypeError):
        return None


def _time(value):
    try:
        return time.fromisoformat(value) if value else None
    except (ValueError, TypeError):
        return None


def _find(items, query):
    q = (query or "").lower().strip()
    if not q:
        return None
    best, best_score = None, 0.0
    for it in items:
        title = it["title"].lower()
        score = 0.9 if (q in title or title in q) else difflib.SequenceMatcher(None, q, title).ratio()
        if score > best_score:
            best, best_score = it, score
    return best if best_score >= 0.5 else None


# ---- actions -----------------------------------------------------------
async def add_item(a, now):
    title = (a.get("title") or "").strip()
    if not title:
        return "I couldn't tell what to add. Can you rephrase?"
    kind = a.get("kind") if a.get("kind") in DEFAULT_OFFSETS else "task"
    due = _date(a.get("due_date"))
    due_time = _time(a.get("due_time"))
    yearly = bool(a.get("yearly")) or kind == "birthday"
    if yearly and due:
        due = rem.next_occurrence(due, now.date())

    raw = a.get("remind_days_before")
    offsets = [int(x) for x in raw if isinstance(x, (int, float)) and 0 <= x <= 60] if isinstance(raw, list) else []
    offsets = offsets or DEFAULT_OFFSETS[kind]
    if due is None:
        offsets = []

    item_id = await db.add_item(kind, title, due, due_time, yearly, offsets)
    rows = rem.build(due, due_time, offsets, now) if due else []
    await db.add_reminders(item_id, rows)

    out = f"Added #{item_id}: {rem.ICONS[kind]} {title} — {rem.when_text(due, due_time, now.date())}"
    if yearly:
        out += " (repeats every year)"
    if rows:
        out += "\n🔔 I'll remind you: " + ", ".join(f"{at:%a %d %b %H:%M}" for at, _ in rows)
    elif due and due < now.date():
        out += "\n⚠️ That date is already in the past, so no reminders."
    elif due:
        out += "\n⚠️ No reminder time is left before it (too close), so I won't ping you in advance."
    return out


async def complete(a):
    item = _find(await db.open_items(), a.get("title"))
    if not item:
        return "I couldn't find that on your list. Try 'done 12' with the # number."
    await db.mark_done(item["id"])
    return f"✅ Marked done: {item['title']}"


async def delete(a):
    item = _find(await db.open_items(), a.get("title"))
    if not item:
        return "I couldn't find that on your list. Try 'delete 12' with the # number."
    await db.delete_item(item["id"])
    return f"🗑 Deleted: {item['title']}"


async def show_list(scope, now):
    scope = scope if scope in ("today", "week", "all") else "week"
    text = rem.agenda(await db.open_items(), now.date(), scope)
    return text or "Nothing on the list."


async def handle(a, now):
    intent = a.get("intent")
    if intent == "add_item":
        return await add_item(a, now)
    if intent == "complete":
        return await complete(a)
    if intent == "delete":
        return await delete(a)
    if intent == "list":
        return await show_list(a.get("scope"), now)
    if intent == "remember":
        text = (a.get("text") or "").strip()
        if text:
            await db.add_note(text)
            return "🧠 Got it, I'll remember that."
    return None


# ---- commands ----------------------------------------------------------
@router.message(Command("start", "help"))
async def cmd_start(m: Message):
    await m.answer(
        "JARVIS online. Just talk to me normally:\n"
        "• 'my cousin's birthday is Dec 4'\n"
        "• 'java assignment due next Thursday'\n"
        "• 'remind me to call the client tomorrow at 11'\n"
        "• 'what do I have this week?'\n"
        "• 'finished the java assignment' or 'done 3'\n\n"
        "Commands: /today /tasks /memory"
    )


@router.message(Command("today"))
async def cmd_today(m: Message):
    await m.answer(await show_list("today", datetime.now(config.TZ)))


@router.message(Command("tasks"))
async def cmd_tasks(m: Message):
    await m.answer((await show_list("all", datetime.now(config.TZ)))[:3900])


@router.message(Command("memory"))
async def cmd_memory(m: Message):
    notes = await db.recent_notes(30)
    await m.answer("\n".join(f"• {n}" for n in notes) or "I don't have any notes yet.")


# ---- natural language --------------------------------------------------
@router.message(F.text)
async def on_text(m: Message):
    text = m.text.strip()
    now = datetime.now(config.TZ)
    await m.bot.send_chat_action(m.chat.id, "typing")
    await db.add_message("user", text)

    shortcut = SHORTCUT.match(text)
    if shortcut:
        verb, item_id = shortcut.group(1).lower(), int(shortcut.group(2))
        item = await db.get_item(item_id)
        if not item:
            reply = f"No item #{item_id}."
        elif verb == "done":
            await db.mark_done(item_id)
            reply = f"✅ Marked done: {item['title']}"
        else:
            await db.delete_item(item_id)
            reply = f"🗑 Deleted: {item['title']}"
        await db.add_message("assistant", reply)
        return await m.answer(reply)

    replies, want_chat = [], False
    for a in await brain.parse(text):
        if a.get("intent") == "chat":
            want_chat = True
            continue
        try:
            result = await handle(a, now)
            if result:
                replies.append(result)
        except Exception:
            log.exception("action failed: %s", a)
            replies.append("⚠️ I couldn't process one part of that.")

    if want_chat or not replies:
        items = rem.agenda(await db.open_items(), now.date(), "all")
        notes = "\n".join(f"- {n}" for n in await db.recent_notes(20))
        replies.append(await brain.chat(await db.recent_messages(8), items[:3000], notes))

    reply = "\n\n".join(replies)
    await db.add_message("assistant", reply)
    await m.answer(reply[:4000])


async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init(config.DATABASE_URL)
    bot = Bot(config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = AsyncIOScheduler(timezone=config.TZ)
    scheduler.add_job(rem.tick, "interval", minutes=1, args=[bot], max_instances=1, coalesce=True)
    scheduler.add_job(rem.briefing, "cron", hour=config.BRIEFING_HOUR, minute=0, args=[bot])
    scheduler.start()

    log.info("JARVIS is running")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
