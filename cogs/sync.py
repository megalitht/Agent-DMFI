import asyncio
from dataclasses import dataclass
from typing import Literal
import discord
from discord.ext import commands
import gspread
from discord import app_commands
from utils import admin_only, is_user_admin, get_admin_error_embed


# =====================================================================
# 1. TABLES DES RÔLES (À REMPLIR PAR RAPPORT À DISCORD & GOOGLE SHEETS)
# =====================================================================

# A. Table des Grades (Colonne G - "Grade")
GRADE_ROLES: dict[str, int | None] = {
    "EVAT": 1507786024653291751,  # Rôle recrue/EVAT retiré à la FGI
    "SDT": 1507794729029337118,
    "1CL": 1507794729742500061,
    "CPL": 1507794728350126170,
    "CCH": 1507794727725170709,
    "CC1": 1507794725606789202,
    "SGT": 1507795079753105469,
    "SCH": 1507795074321219685,
    "ADJ": 1507795081040494632,
    "ADC": 1507795080482914304,
    "MAJ": 1507795267456467014,
    "ASP": 1507795346804179136,
    "SLT": 1507795347823530116,
    "LTN": 1507795348746403840,
    "CNE": 1507795565554172105,
    "CDT": 1507795568112566352,
    "LCL": 1507795576882729071,
    "COL": 1507795578761777222,
    "GDB": 1528074538473226380,
}

# B. Table des Spécialisations (Colonnes N, O, P, Q - Cases à cocher TRUE/FALSE)
SPECIALITE_ROLES: dict[str, dict[str, int | None]] = {
    "MECA": {
        "role_id": 1508213186212528339,
        "col_index": 14,  # Colonne N (anciennement 15)
    },
    "MEDIC": {
        "role_id": 1508213181493809162,
        "col_index": 15,  # Colonne O (anciennement 16)
    },
    "R&P": {
        "role_id": 1508213083397689404,
        "col_index": 16,  # Colonne P (anciennement 17)
    },
    "PILOTE": {
        "role_id": 1508212787820888175,
        "col_index": 17,  # Colonne Q (anciennement 18)
    },
}

# B-bis. Table des Brevets (Colonnes R à AL - Cases à cocher TRUE/FALSE)
# Remplace "None" par l'ID du rôle Discord correspondant.
# Si un brevet reste à None, il sera ignoré lors de la vérification.
BREVET_ROLES: dict[str, dict[str, int | None]] = {
    "FGI":     {"role_id": None, "col_index": 18},  # Colonne R
    "SC1":     {"role_id": None, "col_index": 19},  # Colonne S
    "SC2":     {"role_id": None, "col_index": 20},  # Colonne T
    "CE":      {"role_id": None, "col_index": 21},  # Colonne U
    "VG":      {"role_id": None, "col_index": 22},  # Colonne V
    "MIT":     {"role_id": None, "col_index": 23},  # Colonne W
    "SAPPEUR": {"role_id": None, "col_index": 24},  # Colonne X
    "COM":     {"role_id": None, "col_index": 25},  # Colonne Y
    "TAP":     {"role_id": None, "col_index": 26},  # Colonne Z
    "VBL":     {"role_id": None, "col_index": 27},  # Colonne AA
    "BL":      {"role_id": None, "col_index": 28},  # Colonne AB
    "CDS":     {"role_id": None, "col_index": 29},  # Colonne AC
    "MH-6":    {"role_id": None, "col_index": 30},  # Colonne AD
    "UH-60V":  {"role_id": None, "col_index": 31},  # Colonne AE
    "CH-53D":  {"role_id": None, "col_index": 32},  # Colonne AF
    "NH-90":   {"role_id": None, "col_index": 33},  # Colonne AG
    "TE":      {"role_id": None, "col_index": 34},  # Colonne AH
    "TP":      {"role_id": None, "col_index": 35},  # Colonne AI
    "SPTR":    {"role_id": None, "col_index": 36},  # Colonne AJ
    "BACGN":   {"role_id": None, "col_index": 37},  # Colonne AK
    "BACPN":   {"role_id": None, "col_index": 38},  # Colonne AL
}

# C. Table des Régiments (Colonne N - "Régiment") [Optionnel]
# Laisse les valeurs à None si tu ne veux pas vérifier les régiments.
REGIMENT_ROLES: dict[str, int | None] = {
    "152e RI": None,    # Mettre l'ID du rôle 152e RI (ou laisser None)
    "1er RPIMa": None,  # Mettre l'ID du rôle 1er RPIMa (ou laisser None)
    "4e RHFS": None,    # Mettre l'ID du rôle 4e RHFS (ou laisser None)
}

# D. Métadonnées issues de ton onglet "DATA" (pour mettre à jour #, Catégorie et Requis
# automatiquement si jamais ces cellules ne contiennent pas de formule dans le Sheet)
GRADE_DATA_INFO: dict[str, tuple[int, str, str]] = {
    "GDB": (1, "Officier Général", "Grade sommital"),
    "COL": (2, "Officier Supérieur", "Accord"),
    "LCL": (3, "Officier Supérieur", "Accord"),
    "CDT": (4, "Officier Supérieur", "Accord"),
    "CNE": (5, "Officier Supérieur", "Accord"),
    "LTN": (6, "Officier Subalterne", "Accord"),
    "SLT": (7, "Officier Subalterne", "École Officier"),
    "ASP": (8, "Officier Subalterne", "École Officier"),
    "MAJ": (9, "Sous-Officier", "Dossier"),
    "ADC": (10, "Sous-Officier", "6"),
    "ADJ": (11, "Sous-Officier", "Test instructeur"),
    "SCH": (12, "Sous-Officier", "5"),
    "SGT": (13, "Sous-Officier", "Test compétences"),
    "CC1": (14, "Militaire du Rang", "Dossier"),
    "CCH": (15, "Militaire du Rang", "4"),
    "CPL": (16, "Militaire du Rang", "3"),
    "1CL": (17, "Militaire du Rang", "2"),
    "SDT": (18, "Militaire du Rang", "1"),
    "EVAT": (19, "Militaire du Rang", "FMI"),
}

# =====================================================================
# 2. NUMÉROS DES COLONNES DE L'ONGLET "Recensement" (A=1, B=2, ...)
# =====================================================================

COL_DISCORD_ID = 1   # Colonne A : ID Discord
COL_DISCORD_TAG = 2  # Colonne B : Discord (@pseudo)
COL_ROBLOX = 3       # Colonne C : Roblox
COL_NOM_USAGE = 4    # Colonne D : Nom d'usage
COL_NUMERO = 5       # Colonne E : #
COL_CATEGORIE = 6    # Colonne F : Catégorie
COL_GRADE = 7        # Colonne G : Grade
COL_REQUIS = 10      # Colonne J : Requis
COL_REGIMENT = 14    # Colonne N : Régiment

LIGNE_DEBUT_DONNEES = 2  # La ligne 1 contient les en-têtes


# =====================================================================
# 3. STRUCTURE D'UN CONFLIT ET INTERFACE INTERACTIVE (BOUTONS)
# =====================================================================

@dataclass
class RoleConflict:
    member: discord.Member
    nom_usage: str
    row_number: int
    conflict_type: Literal["GRADE", "SPECIALITE", "BREVET", "REGIMENT"]
    label: str           # Ex: "Grade", "PILOTE", "Régiment"
    discord_value: str   # Ex: "CPL", "TRUE", "152e RI"
    sheet_value: str     # Ex: "1CL", "FALSE", "Aucun"
    target_col: int      # Numéro de la colonne à modifier dans Google Sheets


class ConflictResolutionView(discord.ui.View):
    def __init__(
        self,
        author: discord.Member,
        worksheet: gspread.Worksheet,
        conflicts: list[RoleConflict],
        missing_in_discord: int,
    ):
        super().__init__(timeout=900)  # Expire au bout de 15 minutes d'inactivité
        self.author = author
        self.worksheet = worksheet
        self.conflicts = conflicts
        self.missing_in_discord = missing_in_discord
        self.current_index = 0
        self.resolved_count = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Seul l'auteur de la commande peut utiliser ces boutons.", ephemeral=True
            )
            return False
        return True

    def build_current_embed(self) -> discord.Embed:
        if self.current_index >= len(self.conflicts):
            return discord.Embed(
                title="✅ Synchronisation DMFI terminée",
                description=(
                    f"Tous les conflits ont été passés en revue !\n"
                    f"• **Corrections appliquées :** `{self.resolved_count}/{len(self.conflicts)}`\n"
                    f"• **Ignorés :** `{len(self.conflicts) - self.resolved_count}`\n"
                    f"• **Membres du Sheet absents du Discord :** `{self.missing_in_discord}`"
                ),
                color=discord.Color.green(),
            )

        c = self.conflicts[self.current_index]
        embed = discord.Embed(
            title=f"⚠️ Conflit détecté ({self.current_index + 1}/{len(self.conflicts)})",
            description=(
                f"**Joueur :** {c.member.mention} (`{c.member.name}`)\n"
                f"**Nom d'usage (Sheet) :** `{c.nom_usage}`\n"
                f"**Ligne Google Sheets :** `{c.row_number}`\n"
                f"**Type de conflit :** `{c.label}`"
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="🔵 Sur Discord",
            value=f"**`{c.discord_value}`**",
            inline=True,
        )
        embed.add_field(
            name="🟢 Sur Google Sheets",
            value=f"**`{c.sheet_value}`**",
            inline=True,
        )
        embed.set_footer(
            text=f"Membres du Sheet non trouvés sur Discord : {self.missing_in_discord}"
        )
        return embed

    async def _advance(self, interaction: discord.Interaction):
        self.current_index += 1
        if self.current_index >= len(self.conflicts):
            for child in self.children:
                child.disabled = True
        await interaction.edit_original_response(embed=self.build_current_embed(), view=self)

    @discord.ui.button(
        label="Discord est valide (Maj Sheet)",
        style=discord.ButtonStyle.primary,
        emoji="🔵",
    )
    async def validate_discord(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        c = self.conflicts[self.current_index]

        if c.conflict_type == "GRADE":
            # Si le joueur a plusieurs grades sur Discord (ex: "CPL, 1CL"), on prend le premier
            new_grade = "" if c.discord_value == "Aucun" else c.discord_value.split(",")[0].strip()
            await asyncio.to_thread(
                self.worksheet.update_cell, c.row_number, COL_GRADE, new_grade
            )

        elif c.conflict_type in ("SPECIALITE", "BREVET"):
            # Envoie un vrai booléen Python (True/False) pour cocher/décocher la case Google Sheets
            bool_val = c.discord_value == "TRUE (Coché)"
            await asyncio.to_thread(
                self.worksheet.update_cell, c.row_number, c.target_col, bool_val
            )

        elif c.conflict_type == "REGIMENT":
            new_reg = "" if c.discord_value == "Aucun" else c.discord_value.split(",")[0].strip()
            await asyncio.to_thread(
                self.worksheet.update_cell, c.row_number, COL_REGIMENT, new_reg
            )

        self.resolved_count += 1
        await self._advance(interaction)

    @discord.ui.button(
        label="Google Sheets est valide (Maj Discord)",
        style=discord.ButtonStyle.success,
        emoji="🟢",
    )
    async def validate_sheets(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        c = self.conflicts[self.current_index]
        guild = c.member.guild

        if c.conflict_type == "GRADE":
            # 1. Retirer tous les rôles de grade actuels du joueur
            all_grade_ids = {rid for rid in GRADE_ROLES.values() if rid is not None}
            roles_to_remove = [r for r in c.member.roles if r.id in all_grade_ids]
            if roles_to_remove:
                await c.member.remove_roles(*roles_to_remove, reason="Sync Recensement DMFI (Grade)")

            # 2. Ajouter le rôle du grade indiqué dans le Google Sheets
            target_role_id = GRADE_ROLES.get(c.sheet_value)
            if target_role_id:
                target_role = guild.get_role(target_role_id)
                if target_role:
                    await c.member.add_roles(target_role, reason="Sync Recensement DMFI (Grade)")

        elif c.conflict_type in ("SPECIALITE", "BREVET"):
            source_dict = SPECIALITE_ROLES if c.conflict_type == "SPECIALITE" else BREVET_ROLES
            role_id = source_dict[c.label]["role_id"]
            if role_id:
                target_role = guild.get_role(role_id)
                if target_role:
                    if c.sheet_value == "TRUE (Coché)":
                        await c.member.add_roles(
                            target_role, reason=f"Sync Recensement DMFI ({c.label})"
                        )
                    else:
                        await c.member.remove_roles(
                            target_role, reason=f"Sync Recensement DMFI ({c.label})"
                        )

        elif c.conflict_type == "REGIMENT":
            all_reg_ids = {rid for rid in REGIMENT_ROLES.values() if rid is not None}
            roles_to_remove = [r for r in c.member.roles if r.id in all_reg_ids]
            if roles_to_remove:
                await c.member.remove_roles(*roles_to_remove, reason="Sync Recensement DMFI (Régiment)")

            target_role_id = REGIMENT_ROLES.get(c.sheet_value)
            if target_role_id:
                target_role = guild.get_role(target_role_id)
                if target_role:
                    await c.member.add_roles(target_role, reason="Sync Recensement DMFI (Régiment)")

        self.resolved_count += 1
        await self._advance(interaction)

    @discord.ui.button(label="Ignorer", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_conflict(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self._advance(interaction)


# =====================================================================
# 4. COG DE LA COMMANDE D'ANALYSE
# =====================================================================

class RecensementSyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Fichier JSON du Service Account Google Cloud
        self.gc = gspread.service_account(filename="service_account.json")
        self.spreadsheet_id = "1j8Z5PrqQwMfRE9aFLaQ7VA-ZwUvJqnPeFXAP9ybhvR8"
        self.worksheet_name = "Recensement"

    def _get_sheet_data(self) -> tuple[gspread.Worksheet, list[list[str]]]:
        sh = self.gc.open_by_key(self.spreadsheet_id)
        ws = sh.worksheet(self.worksheet_name)
        return ws, ws.get_all_values()

    @app_commands.command(name="sync", description="Syncronise les role discord au recensement.")
    @app_commands.default_permissions(administrator=True)
    async def sync_recensement(self, interaction: discord.Interaction):
        
        # On répond via l'interaction au lieu de ctx.send
        await interaction.response.send_message("🔍 **Analyse de l'onglet `Recensement` et des membres Discord en cours...**")
        
        # On récupère l'objet message pour que tes 'await msg.edit()' plus bas continuent de fonctionner
        msg = await interaction.original_response()

        try:
            worksheet, rows = await asyncio.to_thread(self._get_sheet_data)
        except Exception as e:
            await msg.edit(content=f"❌ **Impossible de lire le Google Sheets :** `{e}`")
            return

        # Dictionnaires inversés {role_id: "NOM"} pour identifier rapidement les rôles d'un membre
        id_to_grade = {rid: code for code, rid in GRADE_ROLES.items() if rid is not None}
        id_to_regiment = {rid: name for name, rid in REGIMENT_ROLES.items() if rid is not None}

        conflicts: list[RoleConflict] = []
        missing_in_discord = 0

        # Parcours à partir de la ligne 2 (index 1 dans la liste Python)
        for row_number, row in enumerate(rows[LIGNE_DEBUT_DONNEES - 1:], start=LIGNE_DEBUT_DONNEES):
            if not row or len(row) < COL_DISCORD_ID:
                continue

            raw_id = row[COL_DISCORD_ID - 1].strip()
            # Ignore les lignes vides en bas du tableau (lignes 534 à 957)
            if not raw_id.isdigit():
                continue

            discord_id = int(raw_id)
            member = ctx.guild.get_member(discord_id)
            if member is None:
                missing_in_discord += 1
                continue

            nom_usage = row[COL_NOM_USAGE - 1].strip() if len(row) >= COL_NOM_USAGE else member.display_name
            member_role_ids = {r.id for r in member.roles}

            # ---------------------------------------------------------
            # 1. VÉRIFICATION DU GRADE (Colonne G)
            # ---------------------------------------------------------
            sheet_grade = row[COL_GRADE - 1].strip().upper() if len(row) >= COL_GRADE else ""
            sheet_grade_str = sheet_grade if sheet_grade else "Aucun"

            discord_grades = [id_to_grade[rid] for rid in member_role_ids if rid in id_to_grade]
            discord_grade_str = ", ".join(discord_grades) if discord_grades else "Aucun"

            if discord_grade_str != sheet_grade_str:
                conflicts.append(
                    RoleConflict(
                        member=member,
                        nom_usage=nom_usage,
                        row_number=row_number,
                        conflict_type="GRADE",
                        label="Grade",
                        discord_value=discord_grade_str,
                        sheet_value=sheet_grade_str,
                        target_col=COL_GRADE,
                    )
                )

            # ---------------------------------------------------------
            # 2. VÉRIFICATION DES SPÉCIALITÉS (Colonnes O, P, Q, R)
            # ---------------------------------------------------------
            for spec_name, spec_cfg in SPECIALITE_ROLES.items():
                role_id = spec_cfg["role_id"]
                col_idx = spec_cfg["col_index"]

                # Si l'ID du rôle n'est pas encore renseigné dans la config, on passe
                if role_id is None or col_idx is None:
                    continue

                raw_cell = row[col_idx - 1].strip().upper() if len(row) >= col_idx else "FALSE"
                has_in_sheet = raw_cell == "TRUE"
                has_on_discord = role_id in member_role_ids

                if has_on_discord != has_in_sheet:
                    conflicts.append(
                        RoleConflict(
                            member=member,
                            nom_usage=nom_usage,
                            row_number=row_number,
                            conflict_type="SPECIALITE",
                            label=spec_name,
                            discord_value="TRUE (Coché)" if has_on_discord else "FALSE (Décoché)",
                            sheet_value="TRUE (Coché)" if has_in_sheet else "FALSE (Décoché)",
                            target_col=col_idx,
                        )
                    )
            
            # ---------------------------------------------------------
            # 2bis. VÉRIFICATION DES BREVETS (Colonnes R à AL)
            # ---------------------------------------------------------
            for brevet_name, brevet_cfg in BREVET_ROLES.items():
                role_id = brevet_cfg["role_id"]
                col_idx = brevet_cfg["col_index"]

                if role_id is None or col_idx is None:
                    continue

                raw_cell = row[col_idx - 1].strip().upper() if len(row) >= col_idx else "FALSE"
                has_in_sheet = raw_cell == "TRUE"
                has_on_discord = role_id in member_role_ids

                if has_on_discord != has_in_sheet:
                    conflicts.append(
                        RoleConflict(
                            member=member,
                            nom_usage=nom_usage,
                            row_number=row_number,
                            conflict_type="BREVET",
                            label=brevet_name,
                            discord_value="TRUE (Coché)" if has_on_discord else "FALSE (Décoché)",
                            sheet_value="TRUE (Coché)" if has_in_sheet else "FALSE (Décoché)",
                            target_col=col_idx,
                        )
                    )

            # ---------------------------------------------------------
            # 3. VÉRIFICATION DU RÉGIMENT (Colonne M) [Si configuré]
            # ---------------------------------------------------------
            if id_to_regiment:
                sheet_reg = row[COL_REGIMENT - 1].strip() if len(row) >= COL_REGIMENT else ""
                # Ignore "N/A" pour le traiter comme "Aucun"
                sheet_reg_str = sheet_reg if (sheet_reg and sheet_reg.upper() != "N/A") else "Aucun"

                discord_regs = [id_to_regiment[rid] for rid in member_role_ids if rid in id_to_regiment]
                discord_reg_str = ", ".join(discord_regs) if discord_regs else "Aucun"

                if discord_reg_str != sheet_reg_str:
                    conflicts.append(
                        RoleConflict(
                            member=member,
                            nom_usage=nom_usage,
                            row_number=row_number,
                            conflict_type="REGIMENT",
                            label="Régiment",
                            discord_value=discord_reg_str,
                            sheet_value=sheet_reg_str,
                            target_col=COL_REGIMENT,
                        )
                    )

            # ---------------------------------------------------------
            # 3. VÉRIFICATION DU RÉGIMENT (Colonne N) [Si configuré]
            # ---------------------------------------------------------
            if id_to_regiment:
                sheet_reg = row[COL_REGIMENT - 1].strip() if len(row) >= COL_REGIMENT else ""
                sheet_reg_str = sheet_reg if sheet_reg else "Aucun"

                discord_regs = [id_to_regiment[rid] for rid in member_role_ids if rid in id_to_regiment]
                discord_reg_str = ", ".join(discord_regs) if discord_regs else "Aucun"

                if discord_reg_str != sheet_reg_str:
                    conflicts.append(
                        RoleConflict(
                            member=member,
                            nom_usage=nom_usage,
                            row_number=row_number,
                            conflict_type="REGIMENT",
                            label="Régiment",
                            discord_value=discord_reg_str,
                            sheet_value=sheet_reg_str,
                            target_col=COL_REGIMENT,
                        )
                    )

        if not conflicts:
            await msg.edit(
                content=(
                    f"✅ **Aucun conflit de rôle détecté sur les membres présents !**\n"
                    f"*(Note : `{missing_in_discord}` ID(s) du Google Sheets ne sont plus sur le serveur Discord.)*"
                )
            )
            return

        view = ConflictResolutionView(
            author=ctx.author,
            worksheet=worksheet,
            conflicts=conflicts,
            missing_in_discord=missing_in_discord,
        )
        await msg.edit(content=None, embed=view.build_current_embed(), view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(RecensementSyncCog(bot))