import discord
import time
import io
from discord.ext import commands
from discord import app_commands
from utils import admin_only, load_event_data, save_event_data
from database import get_server_config

MSG_ERR_CONFIG = "❌ L'administrateur n'a pas encore configuré ce paramètre. Utilisez `/quickstart`."
MSG_MOD_DESACTIVE = "❌ Ce système n'est pas activé sur ce serveur."

class Event(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Cog Event chargé. Connecté en tant que {self.bot.user}')


# ====================================================
#           Event Enregistrement Dans Vocal
# ====================================================

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        config = get_server_config(member.guild.id)
        if config.get("module_event_active", 1) == 0: return # Bloqué silencieusement
        
        data = load_event_data()
        if not data or not data.get("active"): return

        target_channel_id = data.get("channel_id")
        if not target_channel_id: return
        
        if after.channel and after.channel.id == target_channel_id:
            if before.channel and before.channel.id == target_channel_id: return
            if member.id not in data["participants"]:
                data["participants"].append(member.id)
                save_event_data(data)

    @app_commands.command(name="startevent", description="Démarre l'enregistrement vocal")
    @admin_only
    async def startevent(self, interaction: discord.Interaction):
        config = get_server_config(interaction.guild_id)
        if config.get("module_event_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        voice_id = config.get("event_voice_id")
        if not voice_id:
            await interaction.response.send_message(MSG_ERR_CONFIG, ephemeral=True)
            return

        channel = interaction.guild.get_channel(voice_id)
        if not channel:
            await interaction.response.send_message("❌ Le salon vocal configuré n'existe plus.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        current_data = load_event_data()
        
        if current_data and current_data.get("active"):
            await interaction.followup.send("⚠️ Événement déjà en cours !", ephemeral=True)
            return

        data = {
            "active": True,
            "channel_id": channel.id,
            "start_time": time.time(),
            "participants": [m.id for m in channel.members if not m.bot]
        }
        save_event_data(data)
        
        embed = discord.Embed(title="🎙️ Événement Commencé", description=f"Channel: {channel.mention}", color=discord.Color.green())
        embed.add_field(name="Déjà présents", value=f"{len(data['participants'])} personnes")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="stopevent", description="Arrête l'enregistrement")
    @admin_only
    async def stopevent(self, interaction: discord.Interaction):
        config = get_server_config(interaction.guild_id)
        if config.get("module_event_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        report_id = config.get("event_report_id")
        if not report_id:
            await interaction.response.send_message(MSG_ERR_CONFIG, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        data = load_event_data()
        
        if not data or not data.get("active"):
            await interaction.followup.send("❌ Aucun événement.", ephemeral=True)
            return

        duration_minutes = int((time.time() - data["start_time"]) / 60)
        participant_names = []
        for uid in data["participants"]:
            mem = interaction.guild.get_member(uid)
            participant_names.append(mem.display_name if mem else f"Inconnu ({uid})")

        file_content = f"Rapport Event\nDurée: {duration_minutes} min\nJoueurs: {len(participant_names)}\n---\n" + "\n".join(participant_names)
        discord_file = discord.File(io.BytesIO(file_content.encode('utf-8')), filename="rapport.txt")

        mod_channel = interaction.guild.get_channel(report_id)
        if mod_channel:
            await mod_channel.send(f"📄 **Fin Event**\n⏱️ {duration_minutes} min | 👤 {len(participant_names)} joueurs", file=discord_file)
            await interaction.followup.send("✅ Rapport envoyé.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Salon texte introuvable, voici le fichier :", file=discord_file, ephemeral=True)

        data["active"] = False
        save_event_data(data)

async def setup(bot):
    await bot.add_cog(Event(bot))