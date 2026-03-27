import discord
from discord.ext import commands
from discord import app_commands
from utils import admin_only
from database import add_identity, get_identity, get_all_identities, update_player_data, delete_identity, get_server_config

MSG_ERR_CONFIG = "❌ L'administrateur n'a pas encore configuré ce paramètre. Utilisez `/quickstart`."
MSG_MOD_DESACTIVE = "❌ Ce système n'est pas activé sur ce serveur."

class StaffValidationView(discord.ui.View):
    # ... (Le code de la vue reste identique)
    def __init__(self, user_id, embed_data, guild_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.embed_data = embed_data
        self.guild_id = guild_id

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.green, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        config = get_server_config(self.guild_id)
        role_valide_id = config.get("role_valide_id")
        role_non_valide_id = config.get("role_non_valide_id")
        if role_valide_id and member:
            role_valide = guild.get_role(role_valide_id)
            if role_valide: await member.add_roles(role_valide)
        if role_non_valide_id and member:
            role_non_valide = guild.get_role(role_non_valide_id)
            if role_non_valide: await member.remove_roles(role_non_valide)

        embed = interaction.message.embeds[0]
        data = {f.name: f.value for f in embed.fields}
        naissance = data.get("Naissance", "Inconnu à Inconnu")
        d_naiss = naissance.split(" à ")[0] if " à " in naissance else naissance
        l_naiss = naissance.split(" à ")[1] if " à " in naissance else "Inconnu"
        add_identity(self.guild_id, self.user_id, data.get("Nom"), data.get("Prénom"), data.get("Sexe"), data.get("Nationalité"), d_naiss, l_naiss, data.get("Nom d'usage"))
        embed.color = discord.Color.green()
        embed.title = "✅ ID Validée et Enregistrée"
        await interaction.message.edit(embed=embed, view=None)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.red, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "❌ ID Refusée"
        await interaction.message.edit(embed=embed, view=None)
        member = interaction.guild.get_member(self.user_id)
        if member:
            try: await member.send("Votre demande d'ID a été refusée.")
            except: pass

class PlayerConfirmView(discord.ui.View):
    def __init__(self, embed_data):
        super().__init__(timeout=300)
        self.embed_data = embed_data

    @discord.ui.button(label="Envoyer au staff", style=discord.ButtonStyle.primary, emoji="📩")
    async def send_to_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_server_config(interaction.guild.id)
        salon_admin_id = config.get("salon_admin_id")
        if not salon_admin_id:
            await interaction.response.send_message(MSG_ERR_CONFIG, ephemeral=True)
            return
        admin_channel = interaction.guild.get_channel(salon_admin_id)
        if admin_channel:
            staff_embed = self.embed_data
            staff_embed.title = "🔔 Nouvelle demande d'ID"
            staff_embed.set_author(name=f"Demandeur : {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            view = StaffValidationView(interaction.user.id, self.embed_data, interaction.guild.id)
            await admin_channel.send(embed=staff_embed, view=view)
            await interaction.response.edit_message(content="✅ Envoyé au staff !", embed=None, view=None)
        else:
            await interaction.response.send_message("❌ Salon admin introuvable.", ephemeral=True)

class RPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="createid", description="Créer une ID valide")
    @app_commands.choices(sexe=[app_commands.Choice(name="Masculin", value="Masculin"), app_commands.Choice(name="Féminin", value="Féminin")])
    async def createid(self, interaction: discord.Interaction, nom: str, prénom: str, sexe: app_commands.Choice[str], nationalité: str, date_de_naiss: str, lieu_de_naissance: str, nom_d_usage: str):
        config = get_server_config(interaction.guild.id)
        if config.get("module_rp_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        role_valide_id = config.get("role_valide_id")
        if not role_valide_id:
            await interaction.response.send_message(MSG_ERR_CONFIG, ephemeral=True)
            return
            
        if any(role.id == role_valide_id for role in interaction.user.roles):
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

    @app_commands.command(name="myid", description="Afficher ma carte d'identité")
    async def id(self, interaction: discord.Interaction):
        config = get_server_config(interaction.guild.id)
        if config.get("module_rp_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        data = get_identity(interaction.guild.id, interaction.user.id)
        if not data:
            await interaction.response.send_message("❌ Vous n'avez pas encore d'ID enregistrée. Utilisez `/createid`.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🪪 Carte d'Identité - {interaction.user.display_name}", color=discord.Color.blue())
        embed.add_field(name="Nom", value=data[2], inline=True)
        embed.add_field(name="Prénom", value=data[3], inline=True)
        embed.add_field(name="Sexe", value=data[4], inline=True)
        embed.add_field(name="Nationalité", value=data[5], inline=True)
        embed.add_field(name="Date de naissance", value=data[6], inline=True)
        embed.add_field(name="Lieu de naissance", value=data[7], inline=True)
        embed.add_field(name="Nom d'usage", value=data[8], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="get_id", description="Consulter la carte d'identité d'un joueur")
    @admin_only
    async def get_id(self, interaction: discord.Interaction, cible: discord.Member):
        config = get_server_config(interaction.guild.id)
        if config.get("module_rp_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        data = get_identity(interaction.guild.id, cible.id)
        if not data:
            await interaction.response.send_message(f"❌ Aucune information trouvée.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🪪 Fiche d'Identité - {cible.display_name}", color=discord.Color.gold())
        embed.set_thumbnail(url=cible.display_avatar.url)
        embed.add_field(name="Nom", value=data[2], inline=True)
        embed.add_field(name="Prénom", value=data[3], inline=True)
        embed.add_field(name="Sexe", value=data[4], inline=True)
        embed.add_field(name="Nationalité", value=data[5], inline=True)
        embed.add_field(name="Date de Naissance", value=data[6], inline=True)
        embed.add_field(name="Lieu de Naissance", value=data[7], inline=True)
        embed.add_field(name="Nom d'usage", value=data[8] if data[8] else "Aucun", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="adm_edit_id", description="Modifier la carte d'un joueur")
    @app_commands.choices(champ=[
            app_commands.Choice(name="Nom", value="nom"),
            app_commands.Choice(name="Prénom", value="prenom"),
            app_commands.Choice(name="Sexe", value="sexe"),
            app_commands.Choice(name="Nationalité", value="nationalite"),
            app_commands.Choice(name="Date de naissance", value="date_naiss"),
            app_commands.Choice(name="Lieu de naissance", value="lieu_naiss"),
            app_commands.Choice(name="Nom d'usage", value="nom_usage")
    ])
    @admin_only
    async def adm_edit_id(self, interaction: discord.Interaction, cible: discord.Member, champ: app_commands.Choice[str], nouvelle_valeur: str):
        config = get_server_config(interaction.guild.id)
        if config.get("module_rp_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        success = update_player_data(interaction.guild.id, cible.id, champ.value, nouvelle_valeur)
        if success: await interaction.response.send_message(f"✅ La carte de {cible.mention} a été mise à jour.", ephemeral=True)
        else: await interaction.response.send_message(f"❌ Joueur introuvable dans la base.", ephemeral=True)

    @app_commands.command(name="adm_delete_id", description="Supprimer la carte d'un joueur")
    @admin_only
    async def adm_delete_id(self, interaction: discord.Interaction, cible: discord.Member):
        config = get_server_config(interaction.guild.id)
        if config.get("module_rp_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        success = delete_identity(interaction.guild.id, cible.id)
        if success: await interaction.response.send_message(f"🗑️ La carte de {cible.mention} a été supprimée.", ephemeral=True)
        else: await interaction.response.send_message(f"❌ Joueur introuvable.", ephemeral=True)

    @app_commands.command(name="adm_addid", description="Créer une carte manuellement")
    @app_commands.choices(sexe=[app_commands.Choice(name="Masculin", value="Masculin"), app_commands.Choice(name="Féminin", value="Féminin")])
    @admin_only
    async def adm_addid(self, interaction: discord.Interaction, cible: discord.Member, nom: str, prenom: str, sexe: app_commands.Choice[str], nationalite: str, date_naiss: str, lieu_naiss: str, nom_usage: str = "Aucun"):
        config = get_server_config(interaction.guild.id)
        if config.get("module_rp_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        add_identity(interaction.guild.id, cible.id, nom, prenom, sexe.value, nationalite, date_naiss, lieu_naiss, nom_usage)
        await interaction.response.send_message(f"✅ Carte créée manuellement pour {cible.mention}.", ephemeral=True)

    @app_commands.command(name="adm_show_db", description="Afficher la base de données du serveur")
    @admin_only
    async def adm_show_db(self, interaction: discord.Interaction):
        config = get_server_config(interaction.guild.id)
        if config.get("module_rp_active", 1) == 0:
            await interaction.response.send_message(MSG_MOD_DESACTIVE, ephemeral=True)
            return
            
        results = get_all_identities(interaction.guild.id)
        if not results:
            await interaction.response.send_message("📭 La base de données est vide pour ce serveur.", ephemeral=True)
            return
        
        texte = "📋 **Liste des IDs du serveur :**\n"
        for row in results: texte += f"• <@{row[0]}> : {row[2]} {row[1]}\n"
        
        if len(texte) > 2000:
            import io
            discord_file = discord.File(io.BytesIO(texte.encode('utf-8')), filename="db.txt")
            await interaction.response.send_message(file=discord_file, ephemeral=True)
        else:
            await interaction.response.send_message(texte, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RPSystem(bot))