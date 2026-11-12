from __future__ import annotations
import os
import asyncio
import aiohttp
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands
import gspread
from utils import admin_only, is_user_admin, get_admin_error_embed

ROLE_ADD_ID = 1507786024653291751
ROLE_REMOVE_ID = 1508421388552245409

# Hiérarchie des grades (Grade actuel -> (Prochain grade, Points/Condition par défaut))
GRADES_PROGRESSION = {
    "EVAT": ("SDT", "FMI"),
    "SDT": ("1CL", "1"),
    "1CL": ("CPL", "2"),
    "CPL": ("CCH", "3"),
    "CCH": ("CC1", "4"),
    "CC1": ("SGT", "Dossier"),
    "SGT": ("SCH", "Test compétences"),
    "SCH": ("ADJ", "5"),
    "ADJ": ("ADC", "Test instructeur"),
    "ADC": ("MAJ", "6"),
    "MAJ": ("ASP", "Dossier"),
    "ASP": ("SLT", "École Officier"),
    "SLT": ("LTN", "École Officier"),
    "LTN": ("CNE", "Accord"),
    "CNE": ("CDT", "Accord"),
    "CDT": ("LCL", "Accord"),
    "LCL": ("COL", "Accord"),
    "COL": ("GDB", "Accord"),
    "GDB": ("Max", "Grade sommital"),
}

# --- 1. POP-UP DU JOUEUR (Saisie des informations) ---
class DemandeIntegrationModal(discord.ui.Modal, title="Demande d'intégration DMFI"):
    pseudo_roblox = discord.ui.TextInput(
        label="Pseudo Roblox exact",
        placeholder="Nous voudrions ton @ sur Roblox pour te retrouver facilement",
        required=True,
        max_length=50
    )
    nom_usage = discord.ui.TextInput(
        label="Nom d'usage souhaité",
        placeholder="Vous pouvez mettre une nom RP ou bien mettre un pseudo",
        required=True,
        max_length=50
    )

    def __init__(self, cog: "Moderation"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        mod_channel_id = int(os.getenv("MOD_CHANNEL_ID", 0))
        mod_channel = interaction.guild.get_channel(mod_channel_id)

        if not mod_channel:
            await interaction.followup.send(
                "❌ Le salon de modération est introuvable. Contacte un administrateur.",
                ephemeral=True
            )
            return

        pseudo_saisi = self.pseudo_roblox.value.strip()
        nom_usage_saisi = self.nom_usage.value.strip()

        # Vérification du pseudo Roblox via l'API officielle
        roblox_valide = await self.cog._check_roblox_username(pseudo_saisi)

        # Création de l'Embed envoyé au staff (les champs servent aussi à stocker la donnée)
        embed = discord.Embed(
            title="⏳ Nouvelle demande d'intégration",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="ID Discord", value=str(interaction.user.id), inline=True)
        embed.add_field(name="Pseudo Discord", value=interaction.user.name, inline=True)
        embed.add_field(name="Mention", value=interaction.user.mention, inline=True)
        embed.add_field(name="Pseudo Roblox", value=pseudo_saisi, inline=True)
        embed.add_field(name="Nom d'usage", value=nom_usage_saisi, inline=True)

        if not roblox_valide:
            embed.add_field(
                name="⚠️ Attention",
                value="Le pseudo Roblox est invalide.",
                inline=False
            )
            embed.set_footer(text="⚠️ Attention : Le pseudo Roblox est invalide.")

        await mod_channel.send(embed=embed, view=ModerationActionView(self.cog))

        await interaction.followup.send(
            "✅ Ta demande d'intégration a bien été transmise au staff ! Tu recevras une réponse prochainement.",
            ephemeral=True
        )


# --- 2. BOUTON PERMANENT DANS LE SALON PUBLIC ---
class RecrutementLauncherView(discord.ui.View):
    def __init__(self, cog: "Moderation"):
        super().__init__(timeout=None)  # Permanent
        self.cog = cog

    @discord.ui.button(
        label="Faire ma demande d'intégration",
        style=discord.ButtonStyle.primary,
        emoji="📋",
        custom_id="dmfi:open_integration_modal"
    )
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DemandeIntegrationModal(self.cog))


# --- 3. POP-UP DU MODÉRATEUR (Raison du refus) ---
class RefusModal(discord.ui.Modal, title="Refuser la demande d'intégration"):
    raison = discord.ui.TextInput(
        label="Raison du refus",
        style=discord.TextStyle.paragraph,
        placeholder="Explique pourquoi la demande est refusée (ex: pseudo Roblox introuvable, nom d'usage invalide...)",
        required=True,
        max_length=500
    )

    def __init__(self, message_to_edit: discord.Message, applicant_id: int):
        super().__init__()
        self.message_to_edit = message_to_edit
        self.applicant_id = applicant_id

    async def on_submit(self, interaction: discord.Interaction):
        embed = self.message_to_edit.embeds[0]
        embed.title = "❌ Demande d'intégration refusée"
        embed.color = discord.Color.red()
        embed.add_field(
            name="🛑 Décision Modération",
            value=f"Refusé par {interaction.user.mention}\n**Raison :** {self.raison.value}",
            inline=False
        )

        # Mise à jour du message dans le salon modération et retrait des boutons
        await self.message_to_edit.edit(embed=embed, view=None)

        # Envoi d'un MP au joueur
        membre = interaction.guild.get_member(self.applicant_id)
        if membre:
            try:
                await membre.send(
                    f"❌ Bonjour {membre.mention}, ta demande d'intégration sur **{interaction.guild.name}** a été refusée.\n"
                    f"**Raison :** {self.raison.value}"
                )
            except discord.Forbidden:
                pass  # MP fermés côté joueur

        await interaction.response.send_message("✅ La demande a été refusée et le membre a été notifié.", ephemeral=True)

# --- 4. GESTION DES DOUBLONS (Écraser ou Nouveau recensement) ---
class DuplicateResolutionView(discord.ui.View):
    def __init__(
        self,
        cog: "Moderation",
        original_message: discord.Message,
        applicant_id: int,
        discord_username: str,
        pseudo_roblox: str,
        nom_usage: str,
        duplicate_row: int
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message
        self.applicant_id = applicant_id
        self.discord_username = discord_username
        self.pseudo_roblox = pseudo_roblox
        self.nom_usage = nom_usage
        self.duplicate_row = duplicate_row

    @discord.ui.button(
        label="Écraser l'ancien (Repartir à zéro)",
        style=discord.ButtonStyle.danger,
        emoji="🔄"
    )
    async def overwrite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            _, _, row_num = await asyncio.to_thread(
                self.cog._insert_member_in_sheet,
                str(self.applicant_id),
                self.discord_username,
                self.pseudo_roblox,
                self.nom_usage,
                "overwrite",
                self.duplicate_row
            )
            await self.cog._finalize_integration(
                interaction=interaction,
                message_to_edit=self.original_message,
                applicant_id=self.applicant_id,
                nom_usage=self.nom_usage,
                row_num=row_num,
                action_label="Écrasement & remise à zéro"
            )
            await interaction.edit_original_response(
                content=f"✅ L'ancien recensement (ligne **{row_num}**) a été écrasé et remis à zéro.",
                view=None
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur Google Sheet : `{e}`", ephemeral=True)

    @discord.ui.button(
        label="Recréer un nouveau recensement",
        style=discord.ButtonStyle.primary,
        emoji="➕"
    )
    async def new_row_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            _, _, row_num = await asyncio.to_thread(
                self.cog._insert_member_in_sheet,
                str(self.applicant_id),
                self.discord_username,
                self.pseudo_roblox,
                self.nom_usage,
                "new_row"
            )
            await self.cog._finalize_integration(
                interaction=interaction,
                message_to_edit=self.original_message,
                applicant_id=self.applicant_id,
                nom_usage=self.nom_usage,
                row_num=row_num,
                action_label="Nouvelle ligne créée"
            )
            await interaction.edit_original_response(
                content=f"✅ Un nouveau recensement a été créé à la ligne **{row_num}**.",
                view=None
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur Google Sheet : `{e}`", ephemeral=True)

    @discord.ui.button(
        label="Annuler",
        style=discord.ButtonStyle.secondary,
        emoji="✖️"
    )
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="🛑 Validation annulée. La demande reste en attente.",
            view=None
        )


# --- 5. BOUTONS VALIDER / REFUSER (Salon Modération) ---
class ModerationActionView(discord.ui.View):
    def __init__(self, cog: "Moderation"):
        super().__init__(timeout=None)  # Permanent même si le bot redémarre
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Bloque les clics sur Valider / Refuser pour les non-administrateurs."""
        if not is_user_admin(interaction.user):
            await interaction.response.send_message(embed=get_admin_error_embed(), ephemeral=True)
            return False
        return True

    @discord.ui.button(
        label="Valider",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="dmfi:approve_integration"
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        embed = interaction.message.embeds[0]
        fields = {field.name: field.value for field in embed.fields}

        applicant_id = int(fields["ID Discord"])
        discord_username = fields["Pseudo Discord"]
        pseudo_roblox = fields["Pseudo Roblox"]
        nom_usage = fields["Nom d'usage"]

        try:
            success, msg, row_num = await asyncio.to_thread(
                self.cog._insert_member_in_sheet,
                str(applicant_id),
                discord_username,
                pseudo_roblox,
                nom_usage,
                "check"
            )

            # Si l'utilisateur est déjà recensé, on demande au modérateur ce qu'il veut faire
            if not success:
                view = DuplicateResolutionView(
                    cog=self.cog,
                    original_message=interaction.message,
                    applicant_id=applicant_id,
                    discord_username=discord_username,
                    pseudo_roblox=pseudo_roblox,
                    nom_usage=nom_usage,
                    duplicate_row=row_num
                )
                await interaction.followup.send(
                    f"⚠️ **Attention, cet utilisateur est déjà recensé (Ligne {row_num}) !**\n"
                    f"Voulez-vous écraser l'ancien recensement (il repartira absolument de zéro en **EVAT**, 0 pt, sans spécialisation) "
                    f"ou recréer un nouveau recensement sur une nouvelle ligne ?",
                    view=view,
                    ephemeral=True
                )
                return

            await self.cog._finalize_integration(
                interaction=interaction,
                message_to_edit=interaction.message,
                applicant_id=applicant_id,
                nom_usage=nom_usage,
                row_num=row_num
            )

        except Exception as e:
            print(f"[ERREUR GOOGLE SHEETS] : {e}")
            await interaction.followup.send(f"❌ Erreur Google Sheet : `{e}`", ephemeral=True)

    @discord.ui.button(
        label="Refuser",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="dmfi:reject_integration"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        fields = {field.name: field.value for field in embed.fields}
        applicant_id = int(fields["ID Discord"])

        # Ouvre la pop-up demandant la raison du refus
        await interaction.response.send_modal(RefusModal(interaction.message, applicant_id))
        
class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID")
        self.credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")
        self.gc = gspread.service_account(filename=self.credentials_path)
    
    async def cog_load(self):
        """Enregistre les boutons permanents au démarrage du Cog pour éviter les timeouts."""
        self.bot.add_view(RecrutementLauncherView(self))
        self.bot.add_view(ModerationActionView(self))
        
    def _get_recensement_sheet(self):
        """Ouvre le Google Sheet et cible l'onglet de recensement."""
        sh = self.gc.open_by_key(self.spreadsheet_id)
        try:
            # Attention à l'espace à la fin du nom de l'onglet dans ton fichier
            return sh.worksheet("Recensement ")
        except gspread.WorksheetNotFound:
            return sh.get_worksheet(0)
        
    async def _update_member_roles(self, membre: discord.Member) -> str:
        """Ajoute le rôle de membre recensé et retire le rôle d'attente."""
        guild = membre.guild
        role_to_add = guild.get_role(ROLE_ADD_ID)
        role_to_remove = guild.get_role(ROLE_REMOVE_ID)

        statuts = []
        try:
            if role_to_add and role_to_add not in membre.roles:
                await membre.add_roles(role_to_add, reason="Validation intégration DMFI")
                statuts.append(f"➕ {role_to_add.mention}")
            elif not role_to_add:
                statuts.append("⚠️ Rôle à ajouter introuvable")

            if role_to_remove and role_to_remove in membre.roles:
                await membre.remove_roles(role_to_remove, reason="Validation intégration DMFI")
                statuts.append(f"➖ {role_to_remove.mention}")

            return " | ".join(statuts) if statuts else "✅ Rôles déjà à jour"
        except discord.Forbidden:
            return "⚠️ Échec rôles (rôle du bot trop bas dans la hiérarchie)"
        except discord.HTTPException as e:
            return f"⚠️ Erreur Discord rôles ({e.status})"
        
    async def _check_roblox_username(self, username: str) -> bool:
        """Vérifie sur l'API Roblox si le pseudo (@username) existe et n'est pas banni."""
        clean_username = username.strip().lstrip("@")
        if not clean_username:
            return False

        url = "https://users.roblox.com/v1/usernames/users"
        payload = {
            "usernames": [clean_username],
            "excludeBannedUsers": True
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        timeout = aiohttp.ClientTimeout(total=5)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 1ère requête : Roblox risque de renvoyer 403 pour exiger un token CSRF
                async with session.post(url, json=payload, headers=headers, ssl=False) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return len(data.get("data", [])) > 0
                        
                    # Gestion du blocage de sécurité Roblox (CSRF Token)
                    elif resp.status == 403 and "x-csrf-token" in resp.headers:
                        headers["x-csrf-token"] = resp.headers["x-csrf-token"]
                        
                        # 2ème tentative avec le jeton de sécurité
                        async with session.post(url, json=payload, headers=headers, ssl=False) as resp2:
                            if resp2.status == 200:
                                data = await resp2.json()
                                return len(data.get("data", [])) > 0
                            
                            # Si l'API Roblox ratelimit (429) ou est HS (500+), on force l'acceptation
                            if resp2.status in (429, 500, 502, 503, 504):
                                print(f"[API ROBLOX] API indisponible ({resp2.status}), validation forcée.")
                                return True
                            
                            return False
                    
                    # Si l'API Roblox ratelimit (429) ou est HS (500+) dès la première tentative
                    elif resp.status in (429, 500, 502, 503, 504):
                        print(f"[API ROBLOX] API indisponible ({resp.status}), validation forcée.")
                        return True
                        
                    return False
                    
        except Exception as e:
            print(f"[ERREUR API ROBLOX] : {e}")
            # En cas de crash réseau (DNS, timeout), on ne bloque pas l'utilisateur légitime
            return True
    async def _finalize_integration(
        self,
        interaction: discord.Interaction,
        message_to_edit: discord.Message,
        applicant_id: int,
        nom_usage: str,
        row_num: int,
        action_label: str = "Intégration standard"
    ):
        """Finalise l'intégration Discord (renommage, rôles, MP et mise à jour de l'Embed)."""
        membre = interaction.guild.get_member(applicant_id)
        if membre is None:
            try:
                membre = await interaction.guild.fetch_member(applicant_id)
            except discord.NotFound:
                membre = None

        mp_statut = "✅ MP de confirmation envoyé au joueur"
        rename_statut = "✅ Renommé"
        roles_statut = "⚠️ Membre introuvable"
        nouveau_pseudo = f"[EVAT] {nom_usage}"[:32]

        if membre:
            try:
                await membre.edit(nick=nouveau_pseudo, reason="Validation de la demande d'intégration DMFI")
                rename_statut = f"✅ `{nouveau_pseudo}`"
            except discord.Forbidden:
                rename_statut = "⚠️ Échec (rôle du membre supérieur au bot ou propriétaire)"
            except discord.HTTPException as e:
                rename_statut = f"⚠️ Erreur Discord ({e.status})"

            roles_statut = await self._update_member_roles(membre)

            try:
                await membre.send(
                    f"🎉 Félicitations {membre.mention} ! Ta demande d'intégration sur **{interaction.guild.name}** est **validée**.\n"
                    f"📋 **Statut :** Vérifié et inscrit sur le recensement\n"
                    f"🎖️ Grade **EVAT**\n"
                    f"🏷️ **Nom d'usage :** `{nouveau_pseudo}`\n"
                    f"📅 **Date d'intégration :** {datetime.now().strftime('%d/%m/%Y')}\n"
                    f"📌 Tu peux maintenant attendre la prochaine FGI pour pouvoir accéder aux prochains events."
                )
            except discord.Forbidden:
                mp_statut = "⚠️ MP fermés (le joueur n'a pas pu recevoir la notification)"
        else:
            mp_statut = "⚠️ Membre introuvable sur le serveur"
            rename_statut = "⚠️ Membre introuvable"

        embed = message_to_edit.embeds[0]
        embed.title = "✅ Demande d'intégration validée"
        embed.color = discord.Color.green()
        embed.add_field(
            name="🎖️ Validation & Google Sheet",
            value=(
                f"**Validé par :** {interaction.user.mention}\n"
                f"**Mode :** {action_label}\n"
                f"**Grade :** EVAT (Ligne **{row_num}**)\n"
                f"**Renommage :** {rename_statut}\n"
                f"**Rôles :** {roles_statut}\n"
                f"**Notification :** {mp_statut}"
            ),
            inline=False
        )
        await message_to_edit.edit(embed=embed, view=None)

        await interaction.followup.send(
            f"✅ Membre vérifié et enregistré à la **ligne {row_num}** du Google Sheet ({rename_statut} | {roles_statut} | {mp_statut}).",
            ephemeral=True
        )

    def _insert_member_in_sheet(
        self,
        discord_userid: str,
        discord_username: str,
        roblox_username: str,
        nom_usage: str,
        mode: str = "check",
        overwrite_row: int | None = None
    ) -> tuple[bool, str, int]:
        """
        Gère l'insertion ou l'écrasement dans le Google Sheet :
        - mode="check" : bloque si doublon et renvoie la ligne existante.
        - mode="overwrite" : écrase la ligne `overwrite_row` et remet toute la progression à zéro.
        - mode="new_row" : ignore le doublon et insère sur la première ligne vide.
        """
        ws = self._get_recensement_sheet()

        if mode == "overwrite" and overwrite_row is not None:
            target_row = overwrite_row
        else:
            rows = ws.get("A3:D2000")
            target_row = None

            for index, row in enumerate(rows, start=3):
                col_a = row[0].strip() if len(row) > 0 else ""  # ID Discord
                col_b = row[1].strip() if len(row) > 1 else ""  # Discord
                col_c = row[2].strip() if len(row) > 2 else ""  # Roblox
                col_d = row[3].strip() if len(row) > 3 else ""  # Nom d'usage

                # Vérification anti-doublon uniquement en mode "check"
                if mode == "check":
                    if col_a == str(discord_userid) or (col_c and col_c.lower() == roblox_username.lower()):
                        return False, f"Ce joueur est déjà présent à la ligne **{index}**.", index

                # Première ligne où A, B, C et D sont vides
                if target_row is None and col_a == "" and col_b == "" and col_c == "" and col_d == "":
                    target_row = index
                    if mode == "new_row":
                        break

            if target_row is None:
                target_row = len(rows) + 3

        date_in = datetime.now().strftime("%d/%m/%Y")

        # Écriture / Remise à zéro complète de la ligne (sans toucher aux formules E, F, J, K)
        ws.batch_update(
            [
                {
                    "range": f"A{target_row}:D{target_row}",
                    "values": [[str(discord_userid), f"@{discord_username}", roblox_username, nom_usage]],
                },
                {
                    "range": f"G{target_row}:I{target_row}",
                    "values": [["EVAT", date_in, 0]],
                },
                {
                    "range": f"N{target_row}:Q{target_row}",
                    "values": [[False, False, False, False]],
                },
            ],
            value_input_option="USER_ENTERED",
        )

        return True, "Intégration réussie.", target_row
    
    @commands.hybrid_command(
        name="integrer",
        description="Intègre un nouveau membre dans le Google Sheet de recensement (152e / EVAT)."
    )
    @app_commands.default_permissions(administrator=True)
    @admin_only
    @app_commands.describe(
        membre="Le membre Discord (mention @membre ou directement son ID Discord)",
        pseudo_roblox="Le pseudo Roblox exact du joueur",
        nom_usage="Le nom d'usage choisi pour le joueur"
    )
    
    async def integrer(
        self,
        ctx: commands.Context,
        membre: discord.Member,
        pseudo_roblox: str,
        nom_usage: str
    ):
        await ctx.defer()

        discord_username = membre.name

        try:
            # Correction : ajout de str(membre.id) en premier argument
            success, message, row_num = await asyncio.to_thread(
                self._insert_member_in_sheet,
                str(membre.id),
                discord_username,
                pseudo_roblox,
                nom_usage
            )

            if not success:
                await ctx.send(f"⚠️ **Erreur d'intégration :** {message}")
                return

            # Renommage automatique du membre
            nouveau_pseudo = f"[EVAT] {nom_usage}"[:32]
            rename_statut = f"`{nouveau_pseudo}`"
            try:
                await membre.edit(nick=nouveau_pseudo, reason="Intégration manuelle DMFI")
            except discord.Forbidden:
                rename_statut = "⚠️ Impossible (rôle supérieur au bot ou propriétaire)"
            roles_statut = await self._update_member_roles(membre)

            embed = discord.Embed(
                title="✅ Nouveau membre intégré",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Membre Discord", value=f"{membre.mention} (`{discord_username}`)\nID : `{membre.id}`", inline=False)
            embed.add_field(name="🎮 Pseudo Roblox", value=f"`{pseudo_roblox}`", inline=True)
            embed.add_field(name="🏷️ Surnom appliqué", value=rename_statut, inline=True)
            embed.add_field(name="🎭 Rôles", value=roles_statut, inline=False)
            embed.add_field(name="🎖️ Affectation initiale", value="Grade : **EVAT** | Régiment : **152e RI**", inline=False)
            embed.set_footer(text=f"Ajouté à la ligne {row_num} du Google Sheet")

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ **Erreur lors de l'écriture sur le Google Sheet :** `{e}`")

    @commands.hybrid_command(
        name="setup_recrutement",
        description="Poste le message permanent avec le bouton d'intégration dans ce salon."
    )
    @app_commands.default_permissions(administrator=True)
    @admin_only
    async def setup_recrutement(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🪖 Recensement & Intégration DMFI",
            description=(
                "Bienvenue ! Pour être intégré officiellement dans nos effectifs et inscrit sur le registre :\n\n"
                "1️⃣ Clique sur le bouton **Faire ma demande d'intégration** ci-dessous.\n"
                "2️⃣ Remplis ton **Pseudo Roblox** et ton **Nom d'usage**.\n"
                "3️⃣ Un membre du staff vérifiera et validera ta demande."
            ),
            color=discord.Color.blue()
        )
        await ctx.channel.send(embed=embed, view=RecrutementLauncherView(self))
        await ctx.send("✅ Le panneau d'intégration permanent a été généré.", ephemeral=True)

    @integrer.error
    async def integrer_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MemberNotFound):
            await ctx.send("⚠️ Membre introuvable sur le serveur (vérifie l'ID Discord ou la mention).", ephemeral=True)
        else:
            await ctx.send(f"❌ Une erreur est survenue : `{error}`", ephemeral=True)            

    def _get_member_progression(self, discord_userid: str) -> dict | None:
        """Récupère les données de progression d'un membre depuis la ligne 2 à 2000."""
        ws = self._get_recensement_sheet()
        rows = ws.get("A2:R2000")

        for index, row in enumerate(rows, start=2):
            col_a = row[0].strip() if len(row) > 0 else ""
            if col_a == str(discord_userid):
                def get_col(idx: int) -> str:
                    return row[idx].strip() if len(row) > idx and row[idx] else ""

                specs = []
                for idx, label in [(13, "MECA"), (14, "MEDIC"), (15, "R&P"), (16, "PILOTE")]:
                    if get_col(idx).upper() == "TRUE":
                        specs.append(label)

                return {
                    "row": index,
                    "roblox": get_col(2) or "N/A",
                    "nom_usage": get_col(3) or "N/A",
                    "categorie": get_col(5) or "N/A",
                    "grade": get_col(6) or "EVAT",
                    "date_in": get_col(7) or "N/A",
                    "points_raw": get_col(8),
                    "requis_raw": get_col(9),
                    "regiment": get_col(12) or "N/A",
                    "specs": specs,
                }
        return None

    @commands.hybrid_command(
        name="progression",
        description="Affiche la progression de grade et les statistiques d'un membre."
    )
    @app_commands.describe(membre="Le membre dont tu veux voir la progression (optionnel)")
    async def progression(self, ctx: commands.Context, membre: discord.Member = None):
        await ctx.defer()
        cible = membre or ctx.author

        try:
            data = await asyncio.to_thread(self._get_member_progression, str(cible.id))
        except Exception as e:
            await ctx.send(f"❌ Erreur lors de la lecture du Google Sheet : `{e}`", ephemeral=True)
            return

        if not data:
            await ctx.send(
                f"⚠️ Aucun dossier trouvé pour {cible.mention} dans le recensement.",
                ephemeral=True
            )
            return

        grade_actuel = data["grade"]
        prochain_grade, defaut_requis = GRADES_PROGRESSION.get(grade_actuel, ("Inconnu", "N/A"))
        requis_str = data["requis_raw"] or defaut_requis

        # Vérifie si le prérequis est un nombre de points (ex: 1, 2, 3, 4, 5, 6)
        try:
            pts_requis = float(requis_str.replace(",", "."))
            est_numerique = True
        except ValueError:
            pts_requis = 0.0
            est_numerique = False

        if est_numerique and pts_requis > 0:
            try:
                pts_actuels = float(data["points_raw"].replace(",", ".")) if data["points_raw"] else 0.0
            except ValueError:
                pts_actuels = 0.0

            ratio = min(max(pts_actuels / pts_requis, 0.0), 1.0)
            pourcentage = int(round((pts_actuels / pts_requis) * 100))
            blocs_pleins = int(round(ratio * 10))
            barre = "🟩" * blocs_pleins + "⬜" * (10 - blocs_pleins)

            pts_fmt = str(pts_actuels).rstrip("0").rstrip(".") if "." in str(pts_actuels) else str(pts_actuels)
            pts_fmt = pts_fmt.replace(".", ",")
            req_fmt = str(int(pts_requis)) if pts_requis.is_integer() else str(pts_requis).replace(".", ",")

            statut_promo = "\n🎉 **Éligible à la promotion !**" if pourcentage >= 100 else ""
            bloc_avancement = (
                f"`{barre}` **{pourcentage}%**\n"
                f"📊 **Points :** `{pts_fmt} / {req_fmt} pts` ➔ Prochain grade : **{prochain_grade}**"
                f"{statut_promo}"
            )
        else:
            # Grade à condition (EVAT -> FMI, CC1/MAJ -> Dossier, SGT/ADJ -> Test, Officiers -> École/Accord)
            if grade_actuel == "GDB":
                bloc_avancement = "🏆 **Grade sommital atteint.**"
            else:
                bloc_avancement = (
                    f"📋 **Condition requise :** `{requis_str}`\n"
                    f"🎖️ **Prochain grade :** **{prochain_grade}**"
                )

        embed = discord.Embed(
            title=f"🪖 Dossier & Progression — {data['nom_usage']}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=cible.display_avatar.url)
        embed.add_field(name="👤 Membre", value=f"{cible.mention}\nRoblox : `{data['roblox']}`", inline=True)
        embed.add_field(name="🎖️ Grade actuel", value=f"**{grade_actuel}**\n({data['categorie']})", inline=True)
        embed.add_field(name="🛡️ Régiment", value=f"`{data['regiment']}`\nIntégré le : `{data['date_in']}`", inline=True)
        embed.add_field(name="📈 Avancement vers le grade supérieur", value=bloc_avancement, inline=False)

        specs_str = " • ".join(f"`{s}`" for s in data["specs"]) if data["specs"] else "*Aucune spécialisation*"
        embed.add_field(name="🔧 Spécialisations", value=specs_str, inline=False)
        embed.set_footer(text=f"Ligne {data['row']} du recensement DMFI")

        await ctx.send(embed=embed)
        
async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    
