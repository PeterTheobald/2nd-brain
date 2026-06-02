"""
Tests for vault/writer.py.

Dates used:
  2026-06-01 Mon  — ISO week 23
  2026-06-05 Fri  — ISO week 23  (same week as Jun 1)
  2026-06-08 Mon  — ISO week 24  (new week, same month)
  2026-07-01 Wed  — ISO week 27  (new month)

All tests use tmp_path via the vault_dir fixture — never touch the real vault.
"""

import pytest
import frontmatter
import vault.writer as writer_module
from vault.writer import (
    _build_date_block,
    _parse_date_from_header,
    _iso_week,
    _safe_vault_path,
    _write_journal_entry,
    _write_contact_journal,
    execute_actions,
)
from datetime import date


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------

class TestParseDateFromHeader:
    def test_parses_valid_header(self):
        assert _parse_date_from_header("## 2026-06-01 Mon\n") == date(2026, 6, 1)

    def test_returns_none_for_month_header(self):
        assert _parse_date_from_header("# June\n") is None

    def test_returns_none_for_regular_line(self):
        assert _parse_date_from_header("- some entry\n") is None

    def test_returns_none_for_separator(self):
        assert _parse_date_from_header("---\n") is None

    def test_parses_legacy_header_without_hashes(self):
        # Older entries in the vault use a plain "YYYY-MM-DD Ddd" header.
        assert _parse_date_from_header("2026-05-08 Fri\n") == date(2026, 5, 8)

    def test_parses_combined_weekend_header(self):
        assert _parse_date_from_header("## 2026-01-24,25 Sat,Sun\n") == date(2026, 1, 24)

    def test_returns_none_for_impossible_date(self):
        # 2026-04-31 exists in the real vault; must be skipped, not crash.
        assert _parse_date_from_header("2026-04-31 Tue\n") is None
        assert _parse_date_from_header("## 2026-04-31 Tue\n") is None

    def test_does_not_match_date_inside_bullet(self):
        assert _parse_date_from_header("- met on 2026-06-01\n") is None


class TestIsoWeek:
    def test_same_week(self):
        assert _iso_week(date(2026, 6, 1)) == _iso_week(date(2026, 6, 5))

    def test_different_week(self):
        assert _iso_week(date(2026, 6, 5)) != _iso_week(date(2026, 6, 8))


class TestBuildDateBlock:
    def test_first_ever_entry_gets_month_header(self):
        block = _build_date_block(date(2026, 6, 1), "hello", prev_date=None)
        assert "# June" in block
        assert "## 2026-06-01 Mon" in block
        assert "- hello" in block

    def test_no_month_header_same_month(self):
        block = _build_date_block(date(2026, 6, 8), "hello", prev_date=date(2026, 6, 5))
        assert "# June" not in block
        assert "## 2026-06-08 Mon" in block

    def test_week_separator_on_new_week(self):
        block = _build_date_block(date(2026, 6, 8), "hello", prev_date=date(2026, 6, 5))
        assert "---" in block

    def test_no_week_separator_same_week(self):
        block = _build_date_block(date(2026, 6, 5), "hello", prev_date=date(2026, 6, 1))
        assert "---" not in block

    def test_new_month_gets_month_header_not_week_sep(self):
        block = _build_date_block(date(2026, 7, 1), "hello", prev_date=date(2026, 6, 30))
        assert "# July" in block
        assert "---" not in block

    def test_correct_day_abbreviation(self):
        block = _build_date_block(date(2026, 6, 1), "x", prev_date=None)
        assert "## 2026-06-01 Mon" in block


class TestSafeVaultPath:
    def test_allows_path_inside_vault(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        assert _safe_vault_path("ppl/Alex.md") == (vault_dir / "ppl" / "Alex.md").resolve()

    def test_rejects_parent_traversal(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        with pytest.raises(ValueError):
            _safe_vault_path("../../etc/passwd")

    def test_rejects_absolute_path(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        with pytest.raises(ValueError):
            _safe_vault_path("/etc/passwd")

    def test_traversal_action_is_flagged_not_written(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        results = execute_actions(
            [{"type": "journal_entry", "file": "../escape.md",
              "date": "2026-06-01", "content": "x"}]
        )
        assert results[0].startswith("FAILED")
        assert not (vault_dir.parent / "escape.md").exists()


# ---------------------------------------------------------------------------
# Journal writer tests
# ---------------------------------------------------------------------------

class TestWriteJournalEntry:

    def _action(self, date_str, content, filename="Journal 2026.md"):
        return {"type": "journal_entry", "file": filename, "date": date_str, "content": content}

    def test_creates_new_file(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        _write_journal_entry(self._action("2026-06-01", "first entry"))
        text = (vault_dir / "Journal 2026.md").read_text()
        assert "## 2026-06-01 Mon" in text
        assert "- first entry" in text
        assert "# June" in text

    def test_appends_to_existing_date_section(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        journal = vault_dir / "Journal 2026.md"
        journal.write_text(
            "\n# June\n\n## 2026-06-05 Fri\n- first entry\n"
        )
        _write_journal_entry(self._action("2026-06-05", "second entry"))
        text = journal.read_text()
        assert "- first entry" in text
        assert "- second entry" in text
        # Only one date header for this date
        assert text.count("## 2026-06-05") == 1

    def test_new_date_same_week_no_separator(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        journal = vault_dir / "Journal 2026.md"
        journal.write_text("\n# June\n\n## 2026-06-01 Mon\n- old entry\n")
        _write_journal_entry(self._action("2026-06-05", "new entry"))
        text = journal.read_text()
        assert "## 2026-06-05 Fri" in text
        assert "---" not in text
        assert "# June" in text  # existing month header preserved

    def test_new_date_new_week_adds_separator(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        journal = vault_dir / "Journal 2026.md"
        journal.write_text("\n# June\n\n## 2026-06-05 Fri\n- old entry\n")
        _write_journal_entry(self._action("2026-06-08", "new week entry"))
        text = journal.read_text()
        assert "## 2026-06-08 Mon" in text
        assert "---" in text

    def test_new_month_adds_month_header_no_separator(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        journal = vault_dir / "Journal 2026.md"
        journal.write_text("\n# June\n\n## 2026-06-30 Tue\n- june entry\n")
        _write_journal_entry(self._action("2026-07-01", "july entry"))
        text = journal.read_text()
        assert "# July" in text
        assert "## 2026-07-01 Wed" in text
        assert "- july entry" in text
        # Week separator should NOT appear when month header is present
        # (month header provides visual separation)
        assert text.index("# July") < text.index("# June")  # July before June (top-posting)

    def test_new_entry_appears_before_old_entries(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        journal = vault_dir / "Journal 2026.md"
        journal.write_text("\n# June\n\n## 2026-06-01 Mon\n- old entry\n")
        _write_journal_entry(self._action("2026-06-08", "newer entry"))
        text = journal.read_text()
        assert text.index("newer entry") < text.index("old entry")

    def test_existing_content_preserved(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        journal = vault_dir / "Journal 2026.md"
        journal.write_text(
            "\n# June\n\n## 2026-06-01 Mon\n- entry one\n- entry two\n"
        )
        _write_journal_entry(self._action("2026-06-08", "new entry"))
        text = journal.read_text()
        assert "- entry one" in text
        assert "- entry two" in text
        assert "- new entry" in text

    def test_same_month_entry_goes_under_month_header(self, vault_dir, monkeypatch):
        # Regression: a new same-month entry must slot *under* the existing
        # "# June" header, not above it.
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        journal = vault_dir / "Journal 2026.md"
        journal.write_text("\n# June\n\n## 2026-06-05 Fri\n- old entry\n")
        _write_journal_entry(self._action("2026-06-08", "new week entry"))
        text = journal.read_text()
        # Exactly one June header, and it precedes both date sections.
        assert text.count("# June") == 1
        assert text.index("# June") < text.index("## 2026-06-08")
        assert text.index("## 2026-06-08") < text.index("## 2026-06-05")

    def test_week_separator_sits_between_the_two_weeks(self, vault_dir, monkeypatch):
        # Regression: the "---" rule belongs between the newer week and the
        # older week below it, not above the newer entry.
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        journal = vault_dir / "Journal 2026.md"
        journal.write_text("\n# June\n\n## 2026-06-05 Fri\n- old entry\n")
        _write_journal_entry(self._action("2026-06-08", "new week entry"))
        text = journal.read_text()
        sep = text.index("---")
        assert text.index("## 2026-06-08") < sep < text.index("## 2026-06-05")

    def test_active_now_block_preserved_at_top(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        journal = vault_dir / "Journal 2026.md"
        journal.write_text(
            "\nActive Now:\n- [[Some Project]]\n\n# June\n\n## 2026-06-01 Mon\n- old entry\n"
        )
        _write_journal_entry(self._action("2026-07-01", "july entry"))
        text = journal.read_text()
        assert text.startswith("\nActive Now:")
        assert "- [[Some Project]]" in text
        assert "- july entry" in text
        # Active Now must come first
        assert text.index("Active Now") < text.index("july entry")
        assert text.index("july entry") < text.index("old entry")


# ---------------------------------------------------------------------------
# Contact journal writer tests
# ---------------------------------------------------------------------------

class TestWriteContactJournal:

    def _action(self, filename, content, last_contact="2026-06-01"):
        return {
            "type": "contact_journal",
            "file": f"ppl/{filename}",
            "content": content,
            "update_last_contact": last_contact,
            "new_contact": False,
        }

    def _make_contact(self, vault_dir, filename, extra_body=""):
        path = vault_dir / "ppl" / filename
        path.write_text(
            f"---\nName: Test Person\nLastContact:\naliases: []\n---\n\nAGENDA:\n\nJOURNAL:\n{extra_body}"
        )
        return path

    def test_appends_to_journal_section(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        self._make_contact(vault_dir, "Test Person.md")
        _write_contact_journal(self._action("Test Person.md", "2026-06-01 called re: project"))
        text = (vault_dir / "ppl" / "Test Person.md").read_text()
        assert "2026-06-01 called re: project" in text

    def test_updates_last_contact(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        self._make_contact(vault_dir, "Test Person.md")
        _write_contact_journal(self._action("Test Person.md", "some note", last_contact="2026-06-01"))
        post = frontmatter.load(str(vault_dir / "ppl" / "Test Person.md"))
        assert post.metadata["LastContact"] == "2026-06-01"

    def test_preserves_existing_journal_entries(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        self._make_contact(vault_dir, "Test Person.md", extra_body="- 2026-01-01 old entry\n")
        _write_contact_journal(self._action("Test Person.md", "2026-06-01 new entry"))
        text = (vault_dir / "ppl" / "Test Person.md").read_text()
        assert "2026-01-01 old entry" in text
        assert "2026-06-01 new entry" in text

    def test_preserves_agenda_section(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        path = vault_dir / "ppl" / "Test Person.md"
        path.write_text(
            "---\nName: Test Person\nLastContact:\naliases: []\n---\n\nAGENDA:\n- [ ] ask about project\n\nJOURNAL:\n"
        )
        _write_contact_journal(self._action("Test Person.md", "2026-06-01 spoke"))
        text = path.read_text()
        assert "- [ ] ask about project" in text
        assert "2026-06-01 spoke" in text

    def test_creates_journal_section_if_missing(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        path = vault_dir / "ppl" / "Test Person.md"
        path.write_text("---\nName: Test Person\nLastContact:\naliases: []\n---\n\nAGENDA:\n")
        _write_contact_journal(self._action("Test Person.md", "2026-06-01 note"))
        text = path.read_text()
        assert "2026-06-01 note" in text

    def test_missing_file_does_not_raise(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        # Should return silently, not raise
        _write_contact_journal(self._action("Nonexistent Person.md", "some note"))


# ---------------------------------------------------------------------------
# Integration tests: execute_actions
# ---------------------------------------------------------------------------

class TestExecuteActions:

    def test_executes_journal_and_contact_actions(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        (vault_dir / "ppl" / "Alex Carter.md").write_text(
            "---\nName: Alex Carter\nLastContact:\naliases: [alex]\n---\n\nAGENDA:\n\nJOURNAL:\n"
        )
        actions = [
            {
                "type": "contact_journal",
                "file": "ppl/Alex Carter.md",
                "content": "2026-06-01 called re: house",
                "update_last_contact": "2026-06-01",
                "new_contact": False,
            },
            {
                "type": "journal_entry",
                "file": "Journal 2026.md",
                "date": "2026-06-01",
                "content": "called [[Alex Carter]] re: house",
            },
        ]
        results = execute_actions(actions)
        assert len(results) == 2
        journal = (vault_dir / "Journal 2026.md").read_text()
        assert "called [[Alex Carter]] re: house" in journal
        contact = (vault_dir / "ppl" / "Alex Carter.md").read_text()
        assert "2026-06-01 called re: house" in contact

    def test_returns_result_messages(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        actions = [
            {
                "type": "journal_entry",
                "file": "Journal 2026.md",
                "date": "2026-06-01",
                "content": "test entry",
            }
        ]
        results = execute_actions(actions)
        assert results == ["wrote to Journal 2026.md"]

    def test_unknown_action_type_is_ignored(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        actions = [{"type": "future_action_type", "file": "something.md"}]
        results = execute_actions(actions)
        assert results == []

    def test_invalid_date_is_flagged_not_crashed(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        actions = [
            {
                "type": "journal_entry",
                "file": "Journal 2026.md",
                "date": "2026-04-31",  # impossible date
                "content": "bad date entry",
            }
        ]
        results = execute_actions(actions)
        assert len(results) == 1
        assert results[0].startswith("FAILED")
        # Nothing should have been written.
        assert not (vault_dir / "Journal 2026.md").exists()

    def test_one_bad_action_does_not_block_the_others(self, vault_dir, monkeypatch):
        monkeypatch.setattr(writer_module, "VAULT_PATH", vault_dir)
        actions = [
            {
                "type": "journal_entry",
                "file": "Journal 2026.md",
                "date": "2026-13-01",  # invalid month
                "content": "bad",
            },
            {
                "type": "journal_entry",
                "file": "Journal 2026.md",
                "date": "2026-06-01",
                "content": "good entry",
            },
        ]
        results = execute_actions(actions)
        assert results[0].startswith("FAILED")
        assert results[1] == "wrote to Journal 2026.md"
        assert "good entry" in (vault_dir / "Journal 2026.md").read_text()
