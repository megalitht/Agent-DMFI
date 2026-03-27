import discord
from discord.ext import commands
from discord import app_commands
from utils import admin_only
from database import get_server_config

MSG_ERR_CONFIG = "❌ L'administrateur n'a pas encore configuré ce paramètre. Utilisez `/quickstart`."
MSG_MOD_DESACTIVE = "❌ Ce système n'est pas activé sur ce serveur."

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Cog Moderation chargé. Connecté en tant que {self.bot.user}')

    @commands.Cog.listener()
    async def on_member_join(self, member):
        config = get_server_config(member.guild.id)
        if config.get("module_mod_active", 1) == 0: return # Bloqué silencieusement
        
        autoroles_str = config.get("autoroles")
        if not autoroles_str: return
        
        role_ids = [int(rid) for rid in autoroles_str.split(",") if rid.isdigit()]
        roles_to_add = [member.guild.get_role(rid) for rid in role_ids if member.guild.get_role(rid)]
        
        if roles_to_add:
            await member.add_roles(*roles_to_add)

    @app_commands.command(name="annonce", description="Faire une annonce structurée")
    @admin_only
    async def annonce(self, interaction: discord.Interaction, titre: str, sous_titre: str, paragraphe_1: str, paragraphe_2: str = None, paragraphe_3: str = None, image_url: str = None, mention: discord.Role = None):
        config = get_server_config(interaction.guild_id)
        if config.get("module_mod_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        channel_id = config.get("salon_annonce_id")
        if not channel_id:
            await interaction.response.send_message(MSG_ERR_CONFIG, ephemeral=True)
            return
            
        target_channel = interaction.guild.get_channel(channel_id)
        if target_channel is None:
            await interaction.response.send_message("❌ Salon d'annonce introuvable sur le serveur.", ephemeral=True)
            return

        contenu_final = f"# 📢 {titre}\n### {sous_titre}\n\n{paragraphe_1}\n\n"
        if paragraphe_2: contenu_final += f"{paragraphe_2}\n\n"
        if paragraphe_3: contenu_final += f"{paragraphe_3}\n\n"
        if mention: contenu_final += f"{mention.mention}\n\n"
        contenu_final += f"_______\n*Transmis par l'État Major*"
        if image_url: contenu_final += f"\n{image_url}"

        await interaction.response.defer(ephemeral=True)
        try:
            sent_message = await target_channel.send(contenu_final)
            await interaction.followup.send(f"✅ Annonce publiée !")
            for emoji in ["🟩", "🟧", "🟥"]:
                try: await sent_message.add_reaction(emoji)
                except: pass
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {e}")

    @app_commands.command(name="fmi", description="Met à jour les rôles FMI")
    @admin_only
    async def fmi(self, interaction: discord.Interaction, membre1: discord.Member, membre2: discord.Member = None, membre3: discord.Member = None):
        config = get_server_config(interaction.guild_id)
        if config.get("module_fmi_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        add_str = config.get("fmi_add_roles")
        rem_str = config.get("fmi_remove_roles")
        
        if not add_str and not rem_str:
            await interaction.response.send_message(MSG_ERR_CONFIG, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        role_ids = [int(r) for r in add_str.split(",")] if add_str else []
        remove_ids = [int(r) for r in rem_str.split(",")] if rem_str else []
        membres = [m for m in [membre1, membre2, membre3] if m]

        for membre in membres:
            to_add = [interaction.guild.get_role(rid) for rid in role_ids if interaction.guild.get_role(rid)]
            to_remove = [interaction.guild.get_role(rid) for rid in remove_ids if interaction.guild.get_role(rid)]
            try:
                if to_add: await membre.add_roles(*to_add)
                if to_remove: await membre.remove_roles(*to_remove)
            except Exception as e: print(f"Erreur FMI : {e}")

        await interaction.followup.send(f"✅ Rôles FMI mis à jour pour {len(membres)} membre(s) !", ephemeral=True)

    @app_commands.command(name="add_role_id", description="Met le rôle ID Valide manuellement")
    @admin_only
    async def id_manual(self, interaction: discord.Interaction, membre1: discord.Member, membre2: discord.Member = None):
        config = get_server_config(interaction.guild_id)
        if config.get("module_rp_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        role_id = config.get("role_valide_id")
        if not role_id:
            await interaction.response.send_message(MSG_ERR_CONFIG, ephemeral=True)
            return

        role_to_add = interaction.guild.get_role(role_id)
        if not role_to_add:
            await interaction.response.send_message("❌ Le rôle configuré n'existe plus.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        membres = [m for m in [membre1, membre2] if m]
        for membre in membres:
            await membre.add_roles(role_to_add)

        await interaction.followup.send(f"✅ Rôle ajouté à {len(membres)} personne(s) !", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))