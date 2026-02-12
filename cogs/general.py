# cogs/general.py
import discord
from discord.ext import commands
from discord import app_commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Cog General chargé. Connecté en tant que {self.bot.user}')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
  
        if message.content.lower() == 'mec':
            await message.channel.send("oui ?")
        
        # ID Spécifiques pour les salutations
        id_megaliht = 602585381120114698
        id_noxyze = 1087047036853026967
        id_couscous = 673244682276306950

        if message.content.lower() in ['salut', 'bonjour', 'coucou']:
            if message.author.id == id_megaliht:
                await message.channel.send('bien le bonjour mon créateur adoré <3')
            elif message.author.id == id_noxyze:
                await message.channel.send('Bonjour mon général !')
            elif message.author.id == id_couscous:
                await message.channel.send('Salut ma petit sous merde!')
            else:
                await message.channel.send("salut a toi, Soldat !")
        
        if message.content.lower() == 'def.chefdmfi' and message.author.id == id_megaliht:
            await message.channel.send('Le leader de la DMFI est le Général NOXYSE, un homme d\'stupidité...') # J'ai raccourci pour la lisibilité

    @app_commands.command(name="test", description="fait tester le bot")
    async def test(self, interaction: discord.Interaction):
        await interaction.response.send_message("Le bot est a votre service")

    @app_commands.command(name="linkdmfi", description="affiche le lien vers le serveur discord")
    async def link_dmfi(self, interaction: discord.Interaction):
        await interaction.response.send_message("Voici le lien vers le serveur discord : https://discord.gg/w6BXHah993")

    @app_commands.command(name="linkbrm", description="affiche le lien vers le jeu Roblox")
    async def link_brm(self, interaction: discord.Interaction):
        await interaction.response.send_message("Voici le lien vers le jeu brm5 : https://www.roblox.com/fr/games/2916899287/Blackhawk-Rescue-Mission-5")

async def setup(bot):
    await bot.add_cog(General(bot))