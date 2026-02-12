# main.py
import discord
from database import setup_db
import os
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()
setup_db()

# Configuration du bot
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=discord.Intents.all(),
            help_command=None # Désactive l'aide par défaut si tu veux
        )

    async def setup_hook(self):
        # Chargement des extensions (les fichiers dans /cogs)
        extensions = ['cogs.general', 'cogs.moderation', 'cogs.rp_system']
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"Extension chargée : {ext}")
            except Exception as e:
                print(f"Erreur chargement {ext} : {e}")

        # Synchronisation des commandes Slash
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} commands.")
        except Exception as e:
            print(f"Erreur Sync: {e}")

bot = MyBot()

@bot.event
async def on_ready():
    print('================================')
    print(f'Connecté en tant que {bot.user}')
    print('================================')

bot.run(os.getenv('DISCORD_TOKEN'))