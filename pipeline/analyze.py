import json
import re
import anthropic
from datetime import date
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are the filing assistant for a personal knowledge base (Obsidian vault).
Your job is to analyze a note and return a JSON object describing how to file it.

TODAY: {today}

VAULT CONVENTIONS:
- Journal file: "Journal {year}.md" — top-posting, newest entries first
- Contact notes: in ppl/ folder, filename is the person's full name
- All todos use "- [ ] text" format
- Active todos tagged #⭐️, waiting tagged #⏳, untagged = someday
- Write tersely: use "w/" for "with", drop filler words, keep entries to one line
- Use [[Name]] wiki-link format when referencing people or notes

KNOWN CONTACTS (name → filename):
{contact_index}

ACTION TYPES (Phase 1):
1. journal_entry — a general log entry for today's journal
2. contact_journal — log an interaction with a specific person (always paired with a journal_entry cross-link)

RULES:
- If a person is mentioned and you know them, always generate both a contact_journal AND a journal_entry
- If a person is mentioned but not in the contact list, flag them with "new_contact": true in the action
- Keep journal_entry content to one terse line with [[links]]
- Keep contact_journal content to one line starting with the date

Return ONLY valid JSON in this exact structure, no other text:
{{
  "transcript": "<cleaned up version of the input>",
  "actions": [
    {{
      "type": "contact_journal",
      "file": "ppl/Full Name.md",
      "content": "{today} note text here",
      "update_last_contact": "{today}",
      "new_contact": false
    }},
    {{
      "type": "journal_entry",
      "file": "Journal {year}.md",
      "date": "{today}",
      "content": "terse entry w/ [[links]]"
    }}
  ]
}}"""


def _extract_text(message) -> str:
    """Return the first text block from a Claude response, or raise."""
    for block in message.content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return text
    raise ValueError("Claude response contained no text block")


def _parse_json(text: str) -> dict:
    """Parse Claude's JSON reply, tolerating ```json fences and stray prose."""
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} span if the model wrapped it in text.
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end > start:
            return json.loads(s[start : end + 1])
        raise


def analyze(transcript: str, contact_index: dict[str, str]) -> dict:
    today = date.today().isoformat()
    year = date.today().year

    contact_lines = "\n".join(
        f"  - {name} → ppl/{filename}"
        for name, filename in contact_index.items()
    )

    prompt = SYSTEM_PROMPT.format(
        today=today,
        year=year,
        contact_index=contact_lines or "  (none yet)",
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=prompt,
        messages=[{"role": "user", "content": transcript}],
    )

    data = _parse_json(_extract_text(message))
    if not isinstance(data, dict) or not isinstance(data.get("actions"), list):
        raise ValueError("Claude response missing an 'actions' list")
    data.setdefault("transcript", transcript)
    return data
