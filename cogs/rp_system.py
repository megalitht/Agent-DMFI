# cogs/rp_system.py
from database import add_identity, get_identity
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
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        
        # Gestion des rôles
        role_valide = guild.get_role(ID_ROLE_VALIDE)
        role_non_valide = guild.get_role(ID_ROLE_NON_VALIDE)
        if member and role_valide:
            await member.add_roles(role_valide)
            if role_non_valide: await member.remove_roles(role_non_valide)

        # AJOUT AUTOMATIQUE À LA BASE DE DONNÉES
        embed = interaction.message.embeds[0]
        data = {f.name: f.value for f in embed.fields}
        
        # On sépare Date et Lieu qui étaient dans le même champ dans mon exemple précédent
        naissance = data.get("Naissance", "Inconnu à Inconnu")
        d_naiss = naissance.split(" à ")[0] if " à " in naissance else naissance
        l_naiss = naissance.split(" à ")[1] if " à " in naissance else "Inconnu"

        add_identity(
            user_id=self.user_id,
            nom=data.get("Nom"),
            prenom=data.get("Prénom"),
            sexe=data.get("Sexe"),
            nat=data.get("Nationalité"),
            d_naiss=d_naiss,
            l_naiss=l_naiss,
            usage=data.get("Nom d'usage")
        )

        # 3. Mise à jour visuelle
        embed.color = discord.Color.green()
        embed.title = "✅ ID Validée et Enregistrée"
        await interaction.message.edit(embed=embed, view=None)

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

    @app_commands.command(name="adm_addid", description="Ajouter manuellement une ID en base de données")
    @app_commands.describe(cible="Le joueur", sexe="Sexe")
    @app_commands.choices(sexe=[
        app_commands.Choice(name="Masculin", value="Masculin"),
        app_commands.Choice(name="Féminin", value="Féminin")
    ])
    # @admin_only  # Décommente si tu veux limiter cette commande
    async def adm_addid(self, interaction: discord.Interaction, cible: discord.Member, nom: str, prenom: str, sexe: app_commands.Choice[str], nationalite: str, date_naiss: str, lieu_naiss: str, nom_usage: str):
        add_identity(cible.id, nom.upper(), prenom.capitalize(), sexe.value, nationalite, date_naiss, lieu_naiss, nom_usage)
        await interaction.response.send_message(f"✅ L'ID de {cible.mention} a été ajoutée manuellement au SQL.", ephemeral=True)


    @app_commands.command(name="myid", description="Afficher ma carte d'identité")
    async def myid(self, interaction: discord.Interaction):
        data = get_identity(interaction.user.id)
        
        if not data:
            await interaction.response.send_message("❌ Vous n'avez pas encore d'ID enregistrée. Utilisez `/createid`.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🪪 Carte d'Identité - {interaction.user.display_name}", color=discord.Color.blue())
        embed.add_field(name="Nom", value=data[1], inline=True)
        embed.add_field(name="Prénom", value=data[2], inline=True)
        embed.add_field(name="Sexe", value=data[3], inline=True)
        embed.add_field(name="Nationalité", value=data[4], inline=True)
        embed.add_field(name="Date de naissance", value=data[5], inline=True)
        embed.add_field(name="Lieu de naissance", value=data[6], inline=True)
        embed.add_field(name="Nom d'usage", value=data[7], inline=False)
        embed.set_footer(text=f"Validé le {data[8]}")
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(RPSystem(bot))