import os
import re
import tempfile
from datetime import date
from pathlib import Path
import frontmatter

from config import VAULT_PATH


def _safe_vault_path(file: str) -> Path:
    """Resolve a vault-relative path, refusing anything that escapes the vault.

    `file` comes from the LLM's output, so an absolute path or a "../" sequence
    could otherwise direct a write outside the vault.
    """
    base = VAULT_PATH.resolve()
    target = (base / file).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(f"refusing to write outside the vault: {file!r}") from None
    return target


def _atomic_write(path: Path, text: str) -> None:
    """Write text to path atomically.

    Writes to a temp file in the same directory, fsyncs it, then os.replace()s
    it over the target — an atomic rename on the same filesystem. This prevents
    a truncated/corrupted vault file if the process dies mid-write or if Dropbox
    reads the file while it is being written. These files sync to every device,
    so a partial write is effectively unrecoverable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        # Don't leave a stray temp file in the vault on failure.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def execute_actions(actions: list[dict]) -> list[str]:
    """Execute a list of filing actions. Returns a list of result messages."""
    results = []
    for action in actions:
        t = action.get("type")
        try:
            if t == "journal_entry":
                _write_journal_entry(action)
                results.append(f"wrote to {action['file']}")
            elif t == "contact_journal":
                _write_contact_journal(action)
                results.append(f"wrote to {action['file']}")
        except Exception as e:
            # One bad action must not abort the others or crash the confirm.
            results.append(f"FAILED {action.get('file', '?')}: {e}")
    return results


# --- Journal writer ---

_DATE_HEADER_RE = re.compile(r"^(?:## )?(\d{4}-\d{2}-\d{2})\b")


def _parse_date_from_header(line: str) -> date | None:
    """Extract the date from a journal date header.

    Recognizes the canonical "## YYYY-MM-DD Ddd" form and the legacy plain
    "YYYY-MM-DD Ddd" form (no "##") still present in older entries. Returns None
    for non-header lines and for headers whose date is malformed (e.g. an
    impossible 2026-04-31), so a bad line is skipped rather than crashing the
    write.
    """
    m = _DATE_HEADER_RE.match(line)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _iso_week(d: date) -> tuple[int, int]:
    """Return (year, week_number) for ISO week containing date d."""
    return d.isocalendar()[:2]


def _build_date_block(entry_date: date, content: str, prev_date: date | None) -> str:
    """Build the text block to insert for a new date entry.

    The block is written newest-first and is meant to be inserted *above* the
    previous entry (top-posting). Layout, relative to prev_date:

    - New month: a "# Month" header precedes the date — the month header is the
      visual separator, so no week rule is added.
    - Same month, new ISO week: a "---" week separator is appended *below* the
      entry, so it falls between this (newer) week and the older week beneath it.
    - Same month, same week: just the date section.

    A trailing blank line separates this block from whatever follows below.
    """
    need_month = prev_date is None or prev_date.month != entry_date.month
    need_week_sep = (
        prev_date is not None
        and not need_month
        and _iso_week(prev_date) != _iso_week(entry_date)
    )

    day_str = entry_date.strftime("%A")[:3]
    parts = []

    if need_month:
        parts.append(f"# {entry_date.strftime('%B')}\n\n")

    parts.append(f"## {entry_date.isoformat()} {day_str}\n")
    parts.append(f"- {content}\n")

    if need_week_sep:
        parts.append("---\n")

    parts.append("\n")
    return "".join(parts)


def _write_journal_entry(action: dict) -> None:
    try:
        entry_date = date.fromisoformat(action["date"])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"journal_entry has an invalid date: {action.get('date')!r}") from e
    journal_path = _safe_vault_path(action["file"])

    if not journal_path.exists():
        _atomic_write(
            journal_path,
            "\n" + _build_date_block(entry_date, action["content"], None),
        )
        return

    lines = journal_path.read_text(encoding="utf-8").splitlines(keepends=True)

    # Check if today's date header already exists (canonical or legacy form)
    for i, line in enumerate(lines):
        if _parse_date_from_header(line) == entry_date:
            # Append after the existing bullets for this date, before the
            # trailing blank line or the next section, whichever comes first.
            insert_at = i + 1
            while (
                insert_at < len(lines)
                and lines[insert_at].strip() != ""
                and not lines[insert_at].startswith("##")
                and not lines[insert_at].startswith("# ")
                and not lines[insert_at].startswith("---")
            ):
                insert_at += 1
            lines.insert(insert_at, f"- {action['content']}\n")
            _atomic_write(journal_path, "".join(lines))
            return

    # Find the most recent (topmost) date header to decide month/week separators.
    prev_date = None
    for line in lines:
        d = _parse_date_from_header(line)
        if d:
            prev_date = d
            break

    # Find the start of the journal body: after an "Active Now" block if
    # present, otherwise the first header line. Then skip blank lines so we
    # land on the first real content line.
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("Active Now"):
            j = i + 1
            while j < len(lines) and lines[j].strip():
                j += 1
            body_start = j
            break
        if line.startswith("# ") or line.startswith("## "):
            body_start = i
            break
    while body_start < len(lines) and lines[body_start].strip() == "":
        body_start += 1

    need_month = prev_date is None or prev_date.month != entry_date.month

    insert_at = body_start
    if not need_month and insert_at < len(lines) and lines[insert_at].startswith("# "):
        # Same month: slot the new date *under* the existing "# Month" header
        # (and its following blank line) so it becomes that month's newest entry
        # rather than landing above the header.
        insert_at += 1
        if insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1

    block = _build_date_block(entry_date, action["content"], prev_date)
    lines.insert(insert_at, block)
    _atomic_write(journal_path, "".join(lines))


# --- Contact journal writer ---

def _write_contact_journal(action: dict) -> None:
    contact_path = _safe_vault_path(action["file"])

    if not contact_path.exists():
        # The contact must be created first (a create_contact action in Phase 3).
        # Surface this rather than silently reporting success.
        raise FileNotFoundError(f"contact file does not exist: {action['file']}")

    post = frontmatter.load(str(contact_path))
    body = post.content

    # Update LastContact in frontmatter
    if action.get("update_last_contact"):
        post.metadata["LastContact"] = action["update_last_contact"]

    # Insert under the JOURNAL: section header (a line starting with "JOURNAL:"),
    # not the first place the literal "JOURNAL:" happens to appear in some entry.
    lines = body.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("JOURNAL:"):
            lines.insert(i + 1, f"- {action['content']}\n")
            body = "".join(lines)
            break
    else:
        body = body.rstrip("\n") + f"\n\nJOURNAL:\n- {action['content']}\n"

    post.content = body
    _atomic_write(contact_path, frontmatter.dumps(post))
