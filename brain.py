import json
from datetime import datetime, timedelta

from ollama import AsyncClient

import config

client = AsyncClient(host=config.OLLAMA_HOST)

ROUTER_PROMPT = """You are the intent parser of a personal assistant. Today is {today} ({weekday}), timezone {tz}.
Calendar of the next days: {calendar}

Convert the user's message into JSON of the form {{"actions": [ ... ]}}. Each action has an "intent" plus fields:
- add_item: kind (task|deadline|birthday|event), title, due_date (YYYY-MM-DD or null), due_time (HH:MM or null), yearly (true for birthdays/anniversaries), remind_days_before (list of ints, or null for default)
- complete: title (the thing the user finished)
- delete: title
- list: scope ("today" | "week" | "all")
- remember: text (a lasting fact about the user: preferences, people, goals)
- chat: anything else (greetings, questions, small talk, advice requests)

Rules:
- The user writes English, Uzbek, Russian or a mix, often slang or incomplete sentences.
- Resolve relative dates ("tomorrow", "next Thursday") using the calendar above.
- Birthdays: kind=birthday, yearly=true, due_date = the next upcoming occurrence. Title like "Aziza's birthday".
- University deadlines/exams: kind=deadline. Things to do: kind=task. Meetings/calls at a time: kind=event.
- Several requests in one message -> several actions. If unsure, use chat.
- Output JSON only. Keep titles short, in the user's language.

Examples:
User: remind me to call the client tomorrow at 11
{{"actions":[{{"intent":"add_item","kind":"task","title":"Call the client","due_date":"{tomorrow}","due_time":"11:00","yearly":false,"remind_days_before":null}}]}}
User: wassup vastochniy?
{{"actions":[{{"intent":"chat"}}]}}
User: what do I have this week
{{"actions":[{{"intent":"list","scope":"week"}}]}}
User: finished the java assignment
{{"actions":[{{"intent":"complete","title":"java assignment"}}]}}
"""

PERSONA = """You are JARVIS, Vastochniy's personal assistant on Telegram.
Talk like a smart, warm friend: casual, short, no corporate tone. Reply in the language the user writes in (English, Uzbek, Russian or mixed).
Only use the real data below for tasks and dates. Never invent tasks, deadlines or completed work, and never claim you did something you did not do.
If the user greets you, greet back casually and mention what is open or urgent from the data.

Now: {now}

Open items:
{items}

Things you remember about the user:
{notes}"""


async def parse(text):
    now = datetime.now(config.TZ)
    calendar = ", ".join(f"{now + timedelta(days=i):%a %Y-%m-%d}" for i in range(15))
    prompt = ROUTER_PROMPT.format(
        today=f"{now:%Y-%m-%d}",
        weekday=f"{now:%A}",
        tz=str(config.TZ),
        calendar=calendar,
        tomorrow=f"{now + timedelta(days=1):%Y-%m-%d}",
    )
    resp = await client.chat(
        model=config.OLLAMA_MODEL,
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        format="json",
        options={"temperature": 0},
        keep_alive="30m",
    )
    try:
        data = json.loads(resp["message"]["content"])
        actions = data.get("actions") if isinstance(data, dict) else data
        actions = [a for a in actions if isinstance(a, dict) and a.get("intent")]
        return actions or [{"intent": "chat"}]
    except Exception:
        return [{"intent": "chat"}]


async def chat(history, items_text, notes_text):
    system = PERSONA.format(
        now=f"{datetime.now(config.TZ):%A %d %B %Y, %H:%M}",
        items=items_text or "(nothing open)",
        notes=notes_text or "(nothing yet)",
    )
    resp = await client.chat(
        model=config.OLLAMA_MODEL,
        messages=[{"role": "system", "content": system}, *history],
        options={"temperature": 0.7},
        keep_alive="30m",
    )
    return resp["message"]["content"].strip()
