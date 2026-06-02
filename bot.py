import discord
from discord.ext import commands

from config import DISCORD_TOKEN, DISCORD_CHANNEL_ID
from pipeline.analyze import analyze
from vault.writer import execute_actions
from vault.index import build_contact_index

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

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = pending.pop(self.msg_id, None)
        if result is None:
            await interaction.response.send_message("Suggestion expired.", ephemeral=True)
            return
        results = execute_actions(result["actions"])
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
    print(f"Bot ready: {bot.user}")


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

    contact_index = build_contact_index()

    async with message.channel.typing():
        result = analyze(text, contact_index)

    suggestion_msg = await message.channel.send(
        content=format_suggestion(result),
        view=SuggestionView(0),  # placeholder ID, updated below
    )

    # Now we know the real message ID — store it and patch the view
    pending[suggestion_msg.id] = result
    view = SuggestionView(suggestion_msg.id)
    await suggestion_msg.edit(view=view)


bot.run(DISCORD_TOKEN)
