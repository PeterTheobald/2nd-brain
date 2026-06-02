import re
from datetime import date, datetime, timedelta
from pathlib import Path
import frontmatter

from config import VAULT_PATH


def execute_actions(actions: list[dict]) -> list[str]:
    """Execute a list of filing actions. Returns a list of result messages."""
    results = []
    for action in actions:
        t = action["type"]
        if t == "journal_entry":
            _write_journal_entry(action)
            results.append(f"wrote to {action['file']}")
        elif t == "contact_journal":
            _write_contact_journal(action)
            results.append(f"wrote to {action['file']}")
    return results


# --- Journal writer ---

def _parse_date_from_header(line: str) -> date | None:
    """Extract date from a '## YYYY-MM-DD Ddd' header line."""
    m = re.match(r"^## (\d{4}-\d{2}-\d{2})", line)
    if m:
        return date.fromisoformat(m.group(1))
    return None


def _iso_week(d: date) -> tuple[int, int]:
    """Return (year, week_number) for ISO week containing date d."""
    return d.isocalendar()[:2]


def _build_date_block(entry_date: date, content: str, prev_date: date | None) -> str:
    """Build the text block to insert for a new date entry, including any
    month header and week separator needed relative to the previous entry."""
    parts = []

    need_month = prev_date is None or prev_date.month != entry_date.month
    need_week_sep = prev_date is not None and _iso_week(prev_date) != _iso_week(entry_date)

    if need_month:
        parts.append(f"# {entry_date.strftime('%B')}\n")

    if need_week_sep and not need_month:
        parts.append("---\n")

    day_str = entry_date.strftime("%A")[:3]
    parts.append(f"## {entry_date.isoformat()} {day_str}\n")
    parts.append(f"- {content}\n")

    return "\n" + "".join(parts)


def _write_journal_entry(action: dict) -> None:
    entry_date = date.fromisoformat(action["date"])
    journal_path = VAULT_PATH / action["file"]

    if not journal_path.exists():
        journal_path.write_text(f"\n# {entry_date.strftime('%B')}\n\n## {entry_date.isoformat()} {entry_date.strftime('%A')[:3]}\n- {action['content']}\n")
        return

    lines = journal_path.read_text(encoding="utf-8").splitlines(keepends=True)

    # Check if today's date header already exists
    today_header = f"## {entry_date.isoformat()}"
    for i, line in enumerate(lines):
        if line.startswith(today_header):
            # Find the end of this date's entries and append there
            insert_at = i + 1
            while insert_at < len(lines) and not lines[insert_at].startswith("##") and not lines[insert_at].startswith("# ") and not lines[insert_at].startswith("---"):
                insert_at += 1
            lines.insert(insert_at, f"- {action['content']}\n")
            journal_path.write_text("".join(lines), encoding="utf-8")
            return

    # Find the most recent date header in the file to determine separators needed
    prev_date = None
    for line in lines:
        d = _parse_date_from_header(line)
        if d:
            prev_date = d
            break

    # Find insertion point: after "Active Now" block if present, otherwise top
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("Active Now"):
            # Skip past the Active Now block (until blank line followed by content)
            j = i + 1
            while j < len(lines) and lines[j].strip():
                j += 1
            insert_at = j
            break
        if line.startswith("# ") or line.startswith("## "):
            insert_at = i
            break

    block = _build_date_block(entry_date, action["content"], prev_date)
    lines.insert(insert_at, block)
    journal_path.write_text("".join(lines), encoding="utf-8")


# --- Contact journal writer ---

def _write_contact_journal(action: dict) -> None:
    contact_path = VAULT_PATH / action["file"]

    if not contact_path.exists():
        return  # bot should have created the file first via create_contact action

    post = frontmatter.load(str(contact_path))
    body = post.content

    # Update LastContact in frontmatter
    if action.get("update_last_contact"):
        post.metadata["LastContact"] = action["update_last_contact"]

    # Append to JOURNAL section
    if "JOURNAL:" in body:
        body = body.replace("JOURNAL:", f"JOURNAL:\n- {action['content']}", 1)
    else:
        body = body + f"\nJOURNAL:\n- {action['content']}\n"

    post.content = body
    contact_path.write_text(frontmatter.dumps(post), encoding="utf-8")
