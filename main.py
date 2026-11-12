import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

class DMFIBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Indispensable pour résoudre l'ID Discord -> Membre

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # Chargement automatique des Cogs présents dans le dossier ./cogs
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and not filename.startswith("_"):
                await self.load_extension(f"cogs.{filename[:-3]}")
                print(f"[COG] {filename} chargé avec succès.")

        # Synchronisation des commandes Slash (/)
        await self.tree.sync()
        print("[SLASH] Commandes synchronisées.")

    async def on_ready(self):
        print(f"[BOT] Connecté en tant que {self.user} (ID: {self.user.id})")
        print("------")

async def main():
    bot = DMFIBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())