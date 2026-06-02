import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
DISCORD_CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
VAULT_PATH = Path(os.environ["VAULT_PATH"])
