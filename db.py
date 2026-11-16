from pathlib import Path
import asyncpg

_pool = None


async def init(dsn):
    global _pool
    # statement_cache_size=0 keeps it compatible with Supabase's pooler
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, statement_cache_size=0)
    await _pool.execute(Path(__file__).with_name("schema.sql").read_text())


# ---- items -------------------------------------------------------------
async def add_item(kind, title, due_date, due_time, yearly, offsets):
    return await _pool.fetchval(
        "insert into items (kind, title, due_date, due_time, yearly, offsets) "
        "values ($1, $2, $3, $4, $5, $6) returning id",
        kind, title, due_date, due_time, yearly, offsets,
    )


async def open_items():
    return await _pool.fetch(
        "select * from items where not done "
        "order by due_date nulls last, due_time nulls last, id"
    )


async def get_item(item_id):
    return await _pool.fetchrow("select * from items where id = $1", item_id)


async def mark_done(item_id):
    await _pool.execute("update items set done = true where id = $1", item_id)
    await clear_reminders(item_id)


async def delete_item(item_id):
    await _pool.execute("delete from items where id = $1", item_id)


async def past_yearly(today):
    return await _pool.fetch(
        "select * from items where yearly and not done and due_date < $1", today
    )


async def update_due(item_id, new_date):
    await _pool.execute("update items set due_date = $2 where id = $1", item_id, new_date)


# ---- reminders ---------------------------------------------------------
async def add_reminders(item_id, rows):
    if rows:
        await _pool.executemany(
            "insert into reminders (item_id, remind_at, days_before) values ($1, $2, $3)",
            [(item_id, at, d) for at, d in rows],
        )


async def clear_reminders(item_id):
    await _pool.execute("delete from reminders where item_id = $1 and not sent", item_id)


async def due_reminders(now):
    # ignores anything more than 2 days late so a long outage doesn't spam you
    return await _pool.fetch(
        "select r.id, r.days_before, i.kind, i.title, i.due_date, i.due_time "
        "from reminders r join items i on i.id = r.item_id "
        "where not r.sent and not i.done and r.remind_at <= $1 "
        "and r.remind_at > $1 - interval '2 days' order by r.remind_at",
        now,
    )


async def mark_sent(reminder_id):
    await _pool.execute("update reminders set sent = true where id = $1", reminder_id)


# ---- memory ------------------------------------------------------------
async def add_note(content):
    await _pool.execute("insert into notes (content) values ($1)", content)


async def recent_notes(n=20):
    rows = await _pool.fetch("select content from notes order by id desc limit $1", n)
    return [r["content"] for r in reversed(rows)]


async def add_message(role, content):
    await _pool.execute("insert into messages (role, content) values ($1, $2)", role, content)


async def recent_messages(n=8):
    rows = await _pool.fetch("select role, content from messages order by id desc limit $1", n)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
