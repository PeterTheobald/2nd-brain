import asyncio
import logging

import discord
from discord.ext import commands

from config import DISCORD_TOKEN, DISCORD_CHANNEL_ID
from pipeline.analyze import analyze
from vault.writer import execute_actions
from vault.index import build_contact_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("2nd-brain.bot")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Holds pending suggestions keyed by suggestion message ID
pending: dict[int, dict] = {}


def format_suggestion(result: dict) -> str:
    lines = ["📥 **Filing suggestion**", ""]
    lines.append(f"> *{result['transcript']}*")
    lines.append("")
    for action in result["actions"]:
        if action.get("new_contact"):
            lines.append(f"⚠️ New contact detected: **{action['file']}** — not in vault")
        t = action["type"]
        label = {"journal_entry": "JOURNAL", "contact_journal": "JOURNAL"}.get(t, t.upper())
        lines.append(f"→ `{action['file']}` [{label}]")
        lines.append(f"  {action['content']}")
    return "\n".join(lines)


class SuggestionView(discord.ui.View):
    def __init__(self, msg_id: int):
        super().__init__(timeout=300)
        self.msg_id = msg_id

    async def on_timeout(self) -> None:
        # Drop the stale suggestion so memory doesn't grow unbounded.
        pending.pop(self.msg_id, None)

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = pending.pop(self.msg_id, None)
        if result is None:
            await interaction.response.send_message("Suggestion expired.", ephemeral=True)
            return
        try:
            # File writes are blocking IO — keep them off the event loop.
            results = await asyncio.to_thread(execute_actions, result["actions"])
        except Exception:
            logger.exception("Failed to execute actions")
            await interaction.response.edit_message(
                content=format_suggestion(result) + "\n\n⚠️ **Error filing — check logs.**",
                view=None,
            )
            return
        await interaction.response.edit_message(
            content=format_suggestion(result) + "\n\n✅ **Filed:** " + ", ".join(results),
            view=None,
        )

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        pending.pop(self.msg_id, None)
        await interaction.response.edit_message(
            content="❌ Rejected — resubmit with more detail if needed.",
            view=None,
        )


@bot.event
async def on_ready():
    logger.info("Bot ready: %s", bot.user)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    # Phase 2 will handle voice attachments here
    text = message.content.strip()
    if not text:
        return

    try:
        async with message.channel.typing():
            # build_contact_index (file IO) and analyze (network) both block —
            # run them in a thread so the bot stays responsive.
            contact_index = await asyncio.to_thread(build_contact_index)
            result = await asyncio.to_thread(analyze, text, contact_index)
    except Exception:
        logger.exception("Failed to analyze message")
        await message.channel.send(
            "⚠️ Couldn't analyze that — try rephrasing or resubmitting."
        )
        return

    # Send with the view, then patch in the real message ID. The button
    # callbacks read self.msg_id at click time, so no follow-up edit is needed.
    view = SuggestionView(0)
    suggestion_msg = await message.channel.send(content=format_suggestion(result), view=view)
    view.msg_id = suggestion_msg.id
    pending[suggestion_msg.id] = result


def main() -> None:
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
