# cogs/general.py
import discord
import json
from discord.ext import commands
from discord import app_commands
from database import get_server_config

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Cog General chargé. Connecté en tant que {self.bot.user}')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        
        # --- COMMANDES CLASSIQUES ---
        if message.content.lower() == 'mec':
            await message.channel.send("oui ?")
        
        # Identifiants fixes
        id_megaliht = 602585381120114698
        id_noxyze = 1087047036853026967
        id_couscous = 673244682276306950
        id_recon = 1016069184616136805

        if message.content.lower() in ['salut', 'bonjour', 'coucou']:
            if message.author.id == id_megaliht: await message.channel.send('bien le bonjour mon créateur adoré <3')
            elif message.author.id == id_noxyze: await message.channel.send('Bonjour mon général !')
            elif message.author.id == id_couscous: await message.channel.send('Salut bg!')
            elif message.author.id == id_recon: await message.channel.send('é mè t ki toa !')   

            else: await message.channel.send("salut a toi, Soldat !")

        # --- GESTION DU BOT: (SAY) DYNAMIQUE ---
        if message.content.startswith("bot:"):
            contenu = message.content[4:].strip() 
            if contenu:
                await message.delete()
                
                config = get_server_config(message.guild.id)
                webhook_name = config.get("webhook_name")
                if not webhook_name: 
                    webhook_name = "Agent DMFI"

                webhook = await message.channel.create_webhook(name="Assistant Temporaire")
                await webhook.send(content=contenu, username=webhook_name)
                await webhook.delete()

    @app_commands.command(name="test", description="fait tester le bot")
    async def test(self, interaction: discord.Interaction):
        await interaction.response.send_message("Le bot est a votre service")


    @app_commands.command(name="linkbrm", description="affiche le lien vers le jeu Roblox")
    async def link_brm(self, interaction: discord.Interaction):
        await interaction.response.send_message("Voici le lien vers le jeu brm5 : https://www.roblox.com/fr/games/2916899287/Blackhawk-Rescue-Mission-5")

    @app_commands.command(name="code_serveur", description="Affiche la liste des serveurs de jeu ouverts")
    async def code_serveur(self, interaction: discord.Interaction):
        config = get_server_config(interaction.guild.id)
        code_data = config.get("code_serveur")
        rge_data = config.get("rge_serveur", "[0, 0, 0, 0, 0]")

        codes = []
        rge_list = []
        
        if code_data:
            try: codes = json.loads(code_data)
            except json.JSONDecodeError: codes = [code_data]
            
        try: rge_list = json.loads(rge_data)
        except json.JSONDecodeError: rge_list = [0, 0, 0, 0, 0]

        while len(codes) < 5: codes.append("")
        while len(rge_list) < 5: rge_list.append(0)

        desc = ""
        for i in range(5):
            code = codes[i]
            if code:
                rge_status = "✅" if rge_list[i] == 1 else "❌"
                desc += f"**Map n°{i+1} :**\nRGE : {rge_status}\nCode : ```{code}```\n\n"

        if not desc:
            return await interaction.response.send_message("❌ Aucun serveur n'est actuellement ouvert. Revenez plus tard !", ephemeral=True)

        embed = discord.Embed(title="🎮 Liste des codes serveur", description=desc.strip(), color=discord.Color.dark_embed())
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(General(bot))