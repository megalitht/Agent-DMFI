import discord
import os
from dotenv import load_dotenv
from discord.ext import commands
from database import setup_db 

load_dotenv()
setup_db()

# Configuration du Bot

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=discord.Intents.all(),
            help_command=None # Désactive la commande !help par défaut
        )

    async def setup_hook(self):
        # Liste des fichiers dans le dossier "cogs"

        extensions = ['cogs.general', 'cogs.moderation', 'cogs.rp_system', 'cogs.event', 'cogs.dashboard_admin']
        
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"✅ Extension chargée : {ext}")
            except Exception as e:
                print(f"❌ Erreur chargement {ext} : {e}")

        # Synchronisation des commandes Slash (/)
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)} commands synchronisés.")
        except Exception as e:
            print(f"⚠️ Erreur Synch: {e}")

bot = MyBot()

@bot.event
async def on_ready():
    print('================================')
    print(f'Connecté en tant que {bot.user}')
    print(f'ID: {bot.user.id}')
    print('================================')

# Lancement du bot
bot.run(os.getenv('DISCORD_TOKEN'))