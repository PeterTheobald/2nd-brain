import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name!r}. "
            "Copy .env.example to .env and fill it in."
        )
    return value


DISCORD_TOKEN = _require("DISCORD_TOKEN")

try:
    DISCORD_CHANNEL_ID = int(_require("DISCORD_CHANNEL_ID"))
except ValueError as e:
    raise RuntimeError("DISCORD_CHANNEL_ID must be numeric (the Discord channel ID).") from e

ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")

# Optional until Phase 2 (Whisper voice transcription).
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

VAULT_PATH = Path(_require("VAULT_PATH"))
