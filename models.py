"""Shared type definitions for the filing pipeline.

These describe the JSON contract Claude returns and that the vault writer
consumes. They are TypedDicts (plain dicts at runtime), so they add no runtime
behaviour — they document the shape in one place and let a type checker catch
mismatched key access.
"""

from typing import TypedDict


class Action(TypedDict, total=False):
    """A single filing action. Keys present depend on `type`:

    - journal_entry:   type, file, date, content
    - contact_journal: type, file, content, update_last_contact, new_contact
    """

    type: str
    file: str
    content: str
    date: str
    update_last_contact: str
    new_contact: bool


class AnalysisResult(TypedDict):
    """The structured result Claude returns for a transcript."""

    transcript: str
    actions: list[Action]
