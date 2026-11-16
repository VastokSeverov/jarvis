import logging
from datetime import date, datetime, time, timedelta

import config
import db

log = logging.getLogger("jarvis.reminders")
ICONS = {"birthday": "🎂", "deadline": "⏰", "event": "📅", "task": "✅"}


def next_occurrence(d, today):
    """Next date >= today with the same month/day (for birthdays, anniversaries)."""
    year = today.year
    while True:
        try:
            candidate = d.replace(year=year)
        except ValueError:  # Feb 29
            candidate = date(year, 2, 28)
        if candidate >= today:
            return candidate
        year += 1


def build(due_date, due_time, offsets, now):
    """Return [(datetime, days_before)] for reminders that are still in the future."""
    rows = []
    for d in sorted(set(offsets), reverse=True):
        t = due_time if (d == 0 and due_time) else time(config.REMIND_HOUR, 0)
        at = datetime.combine(due_date - timedelta(days=d), t, tzinfo=config.TZ)
        if at > now:
            rows.append((at, d))
    return rows


def when_text(due_date, due_time, today):
    if due_date is None:
        return "no date"
    delta = (due_date - today).days
    if delta == 0:
        base = "today"
    elif delta == 1:
        base = "tomorrow"
    elif delta < 0:
        base = f"overdue ({due_date:%d %b})"
    else:
        base = f"{due_date:%a %d %b}"
    return base + (f", {due_time:%H:%M}" if due_time else "")


def line(item, today):
    icon = ICONS.get(item["kind"], "•")
    return f"#{item['id']} {icon} {item['title']} — {when_text(item['due_date'], item['due_time'], today)}"


def agenda(items, today, scope="week"):
    order = ["⚠️ Overdue", "📍 Today", "➡️ Tomorrow", "🗓 This week", "🔭 Later", "📝 No date"]
    groups = {k: [] for k in order}
    for it in items:
        d = it["due_date"]
        if d is None:
            key = "📝 No date"
        elif d < today:
            key = "⚠️ Overdue"
        elif d == today:
            key = "📍 Today"
        elif d == today + timedelta(days=1):
            key = "➡️ Tomorrow"
        elif d <= today + timedelta(days=7):
            key = "🗓 This week"
        else:
            key = "🔭 Later"
        groups[key].append(it)
    keep = {
        "today": {"⚠️ Overdue", "📍 Today"},
        "week": {"⚠️ Overdue", "📍 Today", "➡️ Tomorrow", "🗓 This week", "📝 No date"},
        "all": set(order),
    }[scope]
    blocks = []
    for key in order:
        if key in keep and groups[key]:
            blocks.append(key + "\n" + "\n".join(line(i, today) for i in groups[key]))
    return "\n\n".join(blocks)


def reminder_text(r):
    d = r["days_before"]
    when = "today" if d == 0 else "tomorrow" if d == 1 else f"in {d} days"
    icon = ICONS.get(r["kind"], "🔔")
    at = f" at {r['due_time']:%H:%M}" if r["due_time"] else ""
    if r["kind"] == "birthday":
        return f"{icon} {r['title']} — {when}{at}"
    return f"{icon} Reminder: {r['title']} — due {when}{at}"


async def roll_yearly(now):
    for it in await db.past_yearly(now.date()):
        new_date = next_occurrence(it["due_date"], now.date())
        await db.update_due(it["id"], new_date)
        await db.clear_reminders(it["id"])
        await db.add_reminders(it["id"], build(new_date, it["due_time"], list(it["offsets"]), now))


async def tick(bot):
    """Runs every minute: sends due reminders. Also keeps the free database awake."""
    try:
        now = datetime.now(config.TZ)
        await roll_yearly(now)
        for r in await db.due_reminders(now):
            await bot.send_message(config.OWNER_ID, reminder_text(r))
            await db.mark_sent(r["id"])
    except Exception:
        log.exception("reminder tick failed")


async def briefing(bot):
    try:
        today = datetime.now(config.TZ).date()
        text = agenda(await db.open_items(), today, "week")
        await bot.send_message(
            config.OWNER_ID,
            "☀️ Good morning, Vastochniy!\n\n" + (text or "Nothing on your list today. Enjoy it."),
        )
    except Exception:
        log.exception("briefing failed")
