"""
Tests for bot.py. Importing bot must NOT start the bot (run() is guarded behind
__main__), so these tests can import it directly and exercise format_suggestion.
"""

import bot


def test_import_does_not_start_bot():
    # If importing bot tried to run(), the test session would hang/fail above.
    assert hasattr(bot, "format_suggestion")
    assert callable(bot.main)


def test_format_suggestion_standard():
    result = {
        "transcript": "called Alex about the house",
        "actions": [
            {
                "type": "contact_journal",
                "file": "ppl/Alex Carter.md",
                "content": "2026-06-01 called re: house",
            },
            {
                "type": "journal_entry",
                "file": "Journal 2026.md",
                "content": "called [[Alex Carter]] re: house",
            },
        ],
    }
    text = bot.format_suggestion(result)
    assert "called Alex about the house" in text
    assert "ppl/Alex Carter.md" in text
    assert "[JOURNAL]" in text


def test_format_suggestion_flags_new_contact():
    result = {
        "transcript": "met Jordan Lee at the meetup",
        "actions": [
            {
                "type": "contact_journal",
                "file": "ppl/Jordan Lee.md",
                "content": "2026-06-01 met at the meetup",
                "new_contact": True,
            },
        ],
    }
    text = bot.format_suggestion(result)
    assert "New contact detected" in text
    assert "Jordan Lee" in text
