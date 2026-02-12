# cogs/rp_system.py
import discord
from discord.ext import commands
from discord import app_commands

ID_ROLE_VALIDE = 1468549988052107391
ID_ROLE_NON_VALIDE = 1470039631260029120
ID_SALON_ADMIN = 1371385524505284629

# --- VUES ---
class StaffValidationView(discord.ui.View):
    def __init__(self, user_id, embed_data):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.embed_data = embed_data

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.green, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.guild.get_member(self.user_id)
        role = interaction.guild.get_role(ID_ROLE_VALIDE)
        role_non = interaction.guild.get_role(ID_ROLE_NON_VALIDE)

        if member and role:
            await member.add_roles(role)
            if role_non: await member.remove_roles(role_non)
            
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "✅ ID Validée par le Staff"
            await interaction.message.edit(embed=embed, view=None)
            try: await member.send(f"Votre ID sur **{interaction.guild.name}** a été acceptée !")
            except: pass
        else:
            await interaction.response.send_message("Erreur : Membre introuvable.", ephemeral=True)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.red, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.guild.get_member(self.user_id)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "❌ ID Refusée"
        await interaction.message.edit(embed=embed, view=None)
        if member:
            try: await member.send("Votre demande d'ID a été refusée.")
            except: pass

class PlayerConfirmView(discord.ui.View):
    def __init__(self, embed_data):
        super().__init__(timeout=300)
        self.embed_data = embed_data

    @discord.ui.button(label="Envoyer au staff", style=discord.ButtonStyle.primary, emoji="📩")
    async def send_to_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        admin_channel = interaction.guild.get_channel(ID_SALON_ADMIN)
        if admin_channel:
            staff_embed = self.embed_data
            staff_embed.title = "🔔 Nouvelle demande d'ID"
            staff_embed.set_author(name=f"Demandeur : {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            
            view = StaffValidationView(interaction.user.id, self.embed_data)
            await admin_channel.send(embed=staff_embed, view=view)
            await interaction.response.edit_message(content="✅ Envoyé au staff !", embed=None, view=None)
        else:
            await interaction.response.send_message("Erreur : Salon admin introuvable.", ephemeral=True)

# --- COG ---
class RPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="createid", description="Créer une ID valide")
    @app_commands.choices(sexe=[
        app_commands.Choice(name="Masculin", value="Masculin"),
        app_commands.Choice(name="Féminin", value="Féminin"),
        app_commands.Choice(name="Autre", value="Autre")
    ])
    async def createid(self, interaction: discord.Interaction, nom: str, prénom: str, sexe: app_commands.Choice[str], nationalité: str, date_de_naiss: str, lieu_de_naissance: str, nom_d_usage: str):
        if any(role.id == ID_ROLE_VALIDE for role in interaction.user.roles):
            await interaction.response.send_message("Vous avez déjà une ID valide.", ephemeral=True)
            return

        embed = discord.Embed(title="🕵️ Vérification ID", description="Aperçu de votre carte.", color=discord.Color.blue())
        embed.add_field(name="Nom", value=nom.upper(), inline=True)
        embed.add_field(name="Prénom", value=prénom.capitalize(), inline=True)
        embed.add_field(name="Sexe", value=sexe.value, inline=True)
        embed.add_field(name="Nationalité", value=nationalité, inline=True)
        embed.add_field(name="Naissance", value=f"{date_de_naiss} à {lieu_de_naissance}", inline=False)
        embed.add_field(name="Nom d'usage", value=nom_d_usage, inline=False)
        
        view = PlayerConfirmView(embed)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RPSystem(bot))