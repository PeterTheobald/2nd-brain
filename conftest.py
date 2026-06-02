import os

# Set dummy env vars so config.py can be imported during tests
# without a real .env file present.
os.environ.setdefault("DISCORD_TOKEN", "test_token")
os.environ.setdefault("DISCORD_CHANNEL_ID", "123456789")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("OPENAI_API_KEY", "test_key")
os.environ.setdefault("VAULT_PATH", "/tmp/test_vault")
