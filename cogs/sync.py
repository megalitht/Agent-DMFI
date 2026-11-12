from __future__ import annotations
import os
import asyncio
from dataclasses import dataclass
from typing import Literal, Optional
import discord
from discord import app_commands
from discord.ext import commands
import gspread

from utils import is_user_admin, get_admin_error_embed, get_recensement_worksheet, rename_with_grade
from data import (
    GRADE_ROLES, SPECIALITE_ROLES, BREVET_ROLES, REGIMENT_ROLES,
    COL_DISCORD_ID, COL_NOM_USAGE, COL_GRADE, COL_REGIMENT, COL_DERNIERE,
    LIGNE_DEBUT_DONNEES, LIGNE_FIN_DONNEES, SPREADSHEET_ID_DEFAUT,
    cellule, lettre_colonne, rang_grade, tous_les_roles_grade,
)

COCHE = "TRUE (Coché)"
DECOCHE = "FALSE (Décoché)"
AUCUN = "Aucun"

TYPE_LABELS = {
    "GRADE": "Grades",
    "SPECIALITE": "Spécialisations",
    "BREVET": "Brevets",
    "REGIMENT": "Régiments",
}


# =====================================================================
# 1. STRUCTURE D'UN CONFLIT
# =====================================================================

@dataclass
class RoleConflict:
    member: discord.Member
    nom_usage: str
    row_number: int
    conflict_type: Literal["GRADE", "SPECIALITE", "BREVET", "REGIMENT"]
    label: str           # Ex: "Grade", "PILOTE", "Régiment"
    discord_value: str   # Ex: "CPL", "TRUE (Coché)", "152e RI"
    sheet_value: str     # Ex: "1CL", "FALSE (Décoché)", "Aucun"
    target_col: int      # Numéro de la colonne à modifier dans Google Sheets
    role_id: int | None = None  # Rôle concerné (spécialisation / brevet)

    def sheet_update(self) -> dict | None:
        """Cellule à écrire si Discord fait foi. None = rien d'exploitable côté Discord."""
        if self.conflict_type in ("SPECIALITE", "BREVET"):
            valeur = self.discord_value == COCHE
        else:
            if self.discord_value == AUCUN:
                return None
            # Plusieurs rôles sur Discord (ex: "CPL, 1CL") : le premier est le plus élevé
            valeur = self.discord_value.split(",")[0].strip()
        return {"range": cellule(self.target_col, self.row_number), "values": [[valeur]]}


def compute_conflicts(
    rows: list[list[str]],
    guild: discord.Guild,
    categorie: str = "ALL",
    only_member_id: int | None = None,
) -> tuple[list[RoleConflict], list[tuple[int, str]], list[discord.Member]]:
    """
    Compare le recensement aux rôles Discord.
    `rows` commence à la ligne LIGNE_DEBUT_DONNEES du Sheet.
    Renvoie (conflits, [(ligne, nom) absents du Discord], [membres gradés non recensés]).
    """
    id_to_grade = {rid: code for code, rid in GRADE_ROLES.items() if rid is not None}
    id_to_regiment = {rid: name for name, rid in REGIMENT_ROLES.items() if rid is not None}

    conflicts: list[RoleConflict] = []
    absents: list[tuple[int, str]] = []
    ids_recenses: set[int] = set()

    def cell(row: list[str], col: int) -> str:
        return row[col - 1].strip() if len(row) >= col and row[col - 1] else ""

    def veut(type_: str) -> bool:
        return categorie in ("ALL", type_)

    for row_number, row in enumerate(rows, start=LIGNE_DEBUT_DONNEES):
        raw_id = cell(row, COL_DISCORD_ID)
        if not raw_id.isdigit():
            continue  # Ligne vide ou sans ID Discord

        discord_id = int(raw_id)
        ids_recenses.add(discord_id)
        if only_member_id is not None and discord_id != only_member_id:
            continue

        nom_usage = cell(row, COL_NOM_USAGE)
        member = guild.get_member(discord_id)
        if member is None:
            absents.append((row_number, nom_usage or raw_id))
            continue

        nom_usage = nom_usage or member.display_name
        member_role_ids = {r.id for r in member.roles}
        base = dict(member=member, nom_usage=nom_usage, row_number=row_number)

        # --- 1. GRADE (Colonne G) ---
        if veut("GRADE"):
            sheet_grade = cell(row, COL_GRADE).upper() or AUCUN
            # Tri du plus haut au plus bas -> affichage stable et "premier = plus élevé"
            discord_grades = sorted(
                (id_to_grade[rid] for rid in member_role_ids if rid in id_to_grade),
                key=rang_grade, reverse=True,
            )
            discord_grade_str = ", ".join(discord_grades) if discord_grades else AUCUN
            if discord_grade_str != sheet_grade:
                conflicts.append(RoleConflict(
                    **base, conflict_type="GRADE", label="Grade",
                    discord_value=discord_grade_str, sheet_value=sheet_grade,
                    target_col=COL_GRADE,
                ))

        # --- 2. SPÉCIALISATIONS (N à Q) et BREVETS (R à AL) ---
        for type_, table in (("SPECIALITE", SPECIALITE_ROLES), ("BREVET", BREVET_ROLES)):
            if not veut(type_):
                continue
            for name, cfg in table.items():
                role_id, col_idx = cfg["role_id"], cfg["col_index"]
                if role_id is None or col_idx is None:
                    continue  # Rôle pas encore renseigné dans data.py
                has_in_sheet = cell(row, col_idx).upper() == "TRUE"
                has_on_discord = role_id in member_role_ids
                if has_on_discord != has_in_sheet:
                    conflicts.append(RoleConflict(
                        **base, conflict_type=type_, label=name,
                        discord_value=COCHE if has_on_discord else DECOCHE,
                        sheet_value=COCHE if has_in_sheet else DECOCHE,
                        target_col=col_idx, role_id=role_id,
                    ))

        # --- 3. RÉGIMENT (Colonne M) [si des rôles sont configurés] ---
        if id_to_regiment and veut("REGIMENT"):
            sheet_reg = cell(row, COL_REGIMENT)
            sheet_reg_str = sheet_reg if (sheet_reg and sheet_reg.upper() != "N/A") else AUCUN
            discord_regs = sorted(id_to_regiment[rid] for rid in member_role_ids if rid in id_to_regiment)
            discord_reg_str = ", ".join(discord_regs) if discord_regs else AUCUN
            if discord_reg_str != sheet_reg_str:
                conflicts.append(RoleConflict(
                    **base, conflict_type="REGIMENT", label="Régiment",
                    discord_value=discord_reg_str, sheet_value=sheet_reg_str,
                    target_col=COL_REGIMENT,
                ))

    # Membres qui portent un rôle de grade sans être dans le recensement
    non_recenses: list[discord.Member] = []
    if only_member_id is None:
        grade_ids = set(id_to_grade)
        non_recenses = [
            m for m in guild.members
            if not m.bot and m.id not in ids_recenses and grade_ids & {r.id for r in m.roles}
        ]

    return conflicts, absents, non_recenses


# =====================================================================
# 2. INTERFACE INTERACTIVE (BOUTONS)
# =====================================================================

class ConflictResolutionView(discord.ui.View):
    def __init__(
        self,
        author: discord.abc.User,
        worksheet: gspread.Worksheet,
        conflicts: list[RoleConflict],
        absents: list[tuple[int, str]],
        non_recenses: list[discord.Member],
    ):
        super().__init__(timeout=900)  # Expire au bout de 15 minutes d'inactivité
        self.author = author
        self.worksheet = worksheet
        self.conflicts = conflicts
        self.absents = absents
        self.non_recenses = non_recenses
        self.message: discord.Message | None = None
        self.current_index = 0
        self.resolved_count = 0
        self.skipped_count = 0
        self.errors: list[str] = []
        self.busy = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Seul l'auteur de la commande peut utiliser ces boutons.", ephemeral=True
            )
            return False
        if self.busy:
            await interaction.response.send_message("⏳ Traitement en cours, patiente...", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    # ---------- Embeds ----------

    def _resume_par_type(self, conflicts: list[RoleConflict]) -> str:
        compte: dict[str, int] = {}
        for c in conflicts:
            compte[c.conflict_type] = compte.get(c.conflict_type, 0) + 1
        return " • ".join(f"{TYPE_LABELS[t]} : `{n}`" for t, n in compte.items()) or "*Aucun*"

    def _annexes(self, embed: discord.Embed):
        if self.absents:
            lignes = ", ".join(f"`{nom}` (l.{ligne})" for ligne, nom in self.absents[:15])
            if len(self.absents) > 15:
                lignes += f" … (+{len(self.absents) - 15})"
            embed.add_field(
                name=f"👻 Recensés absents du Discord ({len(self.absents)})",
                value=lignes[:1020], inline=False,
            )
        if self.non_recenses:
            lignes = ", ".join(m.mention for m in self.non_recenses[:15])
            if len(self.non_recenses) > 15:
                lignes += f" … (+{len(self.non_recenses) - 15})"
            embed.add_field(
                name=f"❓ Gradés sur Discord mais pas dans le recensement ({len(self.non_recenses)})",
                value=lignes[:1020], inline=False,
            )
        if self.errors:
            embed.add_field(
                name=f"⚠️ Erreurs ({len(self.errors)})",
                value="\n".join(self.errors[-5:])[:1020], inline=False,
            )

    def build_current_embed(self, progress: str | None = None) -> discord.Embed:
        total = len(self.conflicts)

        if progress:
            embed = discord.Embed(title="⏳ Synchronisation en cours...", description=progress, color=discord.Color.blurple())
            return embed

        if self.current_index >= total:
            embed = discord.Embed(
                title="✅ Synchronisation DMFI terminée",
                description=(
                    f"• **Corrections appliquées :** `{self.resolved_count}/{total}`\n"
                    f"• **Ignorés :** `{total - self.resolved_count}`"
                ),
                color=discord.Color.green() if not self.errors else discord.Color.orange(),
            )
            self._annexes(embed)
            return embed

        c = self.conflicts[self.current_index]
        embed = discord.Embed(
            title=f"⚠️ Conflit détecté ({self.current_index + 1}/{total})",
            description=(
                f"**Joueur :** {c.member.mention} (`{c.member.name}`)\n"
                f"**Nom d'usage (Sheet) :** `{c.nom_usage}`\n"
                f"**Ligne Google Sheets :** `{c.row_number}`\n"
                f"**Type de conflit :** `{c.label}`"
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(name="🔵 Sur Discord", value=f"**`{c.discord_value}`**", inline=True)
        embed.add_field(name="🟢 Sur Google Sheets", value=f"**`{c.sheet_value}`**", inline=True)
        embed.add_field(
            name=f"📊 Restant ({total - self.current_index})",
            value=self._resume_par_type(self.conflicts[self.current_index:]),
            inline=False,
        )
        self._annexes(embed)
        embed.set_footer(text="Les boutons « Tout » s'appliquent à ce conflit et à tous les suivants.")
        return embed

    async def _refresh(self, progress: str | None = None):
        finished = self.current_index >= len(self.conflicts)
        if finished and not progress:
            self.stop()
        view = None if (finished or progress) else self
        if self.message:
            try:
                await self.message.edit(embed=self.build_current_embed(progress), view=view)
            except discord.HTTPException as e:
                print(f"[SYNC] Impossible de mettre à jour le message : {e}")

    # ---------- Application d'un conflit ----------

    async def _apply_sheet_to_discord(self, c: RoleConflict) -> bool:
        """Le Sheet fait foi : corrige les rôles Discord. Renvoie False si rien n'a pu être fait."""
        guild = c.member.guild
        raison = f"Sync Recensement DMFI ({c.label})"
        try:
            if c.conflict_type in ("GRADE", "REGIMENT"):
                if c.conflict_type == "GRADE":
                    pool, target_id = tous_les_roles_grade(), GRADE_ROLES.get(c.sheet_value)
                else:
                    pool = {rid for rid in REGIMENT_ROLES.values() if rid is not None}
                    target_id = REGIMENT_ROLES.get(c.sheet_value)

                if c.sheet_value != AUCUN and not target_id:
                    self.errors.append(f"• l.{c.row_number} `{c.nom_usage}` : `{c.sheet_value}` n'a pas de rôle dans data.py")
                    return False

                to_remove = [r for r in c.member.roles if r.id in pool and r.id != target_id]
                if to_remove:
                    await c.member.remove_roles(*to_remove, reason=raison)
                if target_id and target_id not in {r.id for r in c.member.roles}:
                    role = guild.get_role(target_id)
                    if role is None:
                        self.errors.append(f"• Rôle `{c.sheet_value}` ({target_id}) introuvable sur le serveur")
                        return False
                    await c.member.add_roles(role, reason=raison)

                if c.conflict_type == "GRADE" and target_id:
                    await rename_with_grade(c.member, c.sheet_value, c.nom_usage, reason=raison)
            else:
                role = guild.get_role(c.role_id) if c.role_id else None
                if role is None:
                    self.errors.append(f"• Rôle `{c.label}` introuvable sur le serveur")
                    return False
                if c.sheet_value == COCHE:
                    await c.member.add_roles(role, reason=raison)
                else:
                    await c.member.remove_roles(role, reason=raison)
            return True
        except discord.Forbidden:
            self.errors.append(f"• {c.member.mention} `{c.label}` : permission refusée (rôle du bot trop bas ?)")
        except discord.HTTPException as e:
            self.errors.append(f"• {c.member.mention} `{c.label}` : erreur Discord {e.status}")
        return False

    async def _apply_discord_to_sheet(self, batch: list[RoleConflict]) -> int:
        """Discord fait foi : écrit toutes les cellules en une seule requête."""
        updates = [u for c in batch if (u := c.sheet_update()) is not None]
        if not updates:
            return 0
        try:
            await asyncio.to_thread(
                self.worksheet.batch_update, updates, value_input_option="USER_ENTERED"
            )
            return len(updates)
        except Exception as e:
            self.errors.append(f"• Écriture Google Sheets impossible : `{e}`")
            return 0

    # ---------- Boutons : un conflit à la fois ----------

    @discord.ui.button(label="Discord est valide (Maj Sheet)", style=discord.ButtonStyle.primary, emoji="🔵", row=0)
    async def validate_discord(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        c = self.conflicts[self.current_index]
        if c.sheet_update() is None:
            await interaction.followup.send(
                "⚠️ Ce membre n'a aucun rôle correspondant sur Discord : je ne vide pas la cellule du Sheet. "
                "Utilise 🟢 pour lui donner le rôle, ou ⏭️ pour ignorer.",
                ephemeral=True,
            )
            return
        self.resolved_count += await self._apply_discord_to_sheet([c])
        self.current_index += 1
        await self._refresh()

    @discord.ui.button(label="Google Sheets est valide (Maj Discord)", style=discord.ButtonStyle.success, emoji="🟢", row=0)
    async def validate_sheets(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        c = self.conflicts[self.current_index]
        if await self._apply_sheet_to_discord(c):
            self.resolved_count += 1
        self.current_index += 1
        await self._refresh()

    @discord.ui.button(label="Ignorer", style=discord.ButtonStyle.secondary, emoji="⏭️", row=0)
    async def skip_conflict(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_index += 1
        await self._refresh()

    # ---------- Boutons : tout le reste d'un coup ----------

    @discord.ui.button(label="Tout : Sheet ➜ Discord", style=discord.ButtonStyle.success, emoji="⏩", row=1)
    async def all_sheets(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.busy = True
        try:
            restants = self.conflicts[self.current_index:]
            for i, c in enumerate(restants, start=1):
                # Un grade vide dans le Sheet ne retire pas les rôles en masse : à traiter à la main
                if c.conflict_type in ("GRADE", "REGIMENT") and c.sheet_value == AUCUN:
                    continue
                if await self._apply_sheet_to_discord(c):
                    self.resolved_count += 1
                if i % 10 == 0:
                    await self._refresh(progress=f"Mise à jour des rôles Discord : `{i}/{len(restants)}`")
            self.current_index = len(self.conflicts)
        finally:
            self.busy = False
        await self._refresh()

    @discord.ui.button(label="Tout : Discord ➜ Sheet", style=discord.ButtonStyle.primary, emoji="⏩", row=1)
    async def all_discord(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.busy = True
        try:
            # Les membres sans rôle sur Discord sont ignorés (on ne vide pas le Sheet en masse)
            self.resolved_count += await self._apply_discord_to_sheet(self.conflicts[self.current_index:])
            self.current_index = len(self.conflicts)
        finally:
            self.busy = False
        await self._refresh()

    @discord.ui.button(label="Arrêter", style=discord.ButtonStyle.danger, emoji="🛑", row=1)
    async def stop_sync(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_index = len(self.conflicts)
        await self._refresh()


# =====================================================================
# 3. COG DE LA COMMANDE /sync
# =====================================================================

class RecensementSyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID") or SPREADSHEET_ID_DEFAUT
        self.credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")
        self.gc = gspread.service_account(filename=self.credentials_path)

    def _get_sheet_data(self) -> tuple[gspread.Worksheet, list[list[str]]]:
        ws = get_recensement_worksheet(self.gc, self.spreadsheet_id)
        plage = f"A{LIGNE_DEBUT_DONNEES}:{lettre_colonne(COL_DERNIERE)}{LIGNE_FIN_DONNEES}"
        return ws, ws.get(plage)

    @app_commands.command(name="sync", description="Détecte et corrige les écarts entre les rôles Discord et le recensement.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.describe(
        categorie="Limiter l'analyse à un type de donnée (par défaut : tout)",
        membre="Limiter l'analyse à un seul membre",
    )
    @app_commands.choices(categorie=[
        app_commands.Choice(name="Tout", value="ALL"),
        app_commands.Choice(name="Grades", value="GRADE"),
        app_commands.Choice(name="Spécialisations", value="SPECIALITE"),
        app_commands.Choice(name="Brevets", value="BREVET"),
        app_commands.Choice(name="Régiments", value="REGIMENT"),
    ])
    async def sync_recensement(
        self,
        interaction: discord.Interaction,
        categorie: Optional[app_commands.Choice[str]] = None,
        membre: Optional[discord.Member] = None,
    ):
        if not is_user_admin(interaction.user):
            await interaction.response.send_message(embed=get_admin_error_embed(), ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        guild = interaction.guild

        try:
            if not guild.chunked:
                await guild.chunk()  # Garantit que tous les membres sont en cache
            worksheet, rows = await asyncio.to_thread(self._get_sheet_data)
        except Exception as e:
            await interaction.followup.send(f"❌ **Impossible de lire le Google Sheets :** `{e}`")
            return

        conflicts, absents, non_recenses = compute_conflicts(
            rows, guild,
            categorie=categorie.value if categorie else "ALL",
            only_member_id=membre.id if membre else None,
        )

        view = ConflictResolutionView(
            author=interaction.user,
            worksheet=worksheet,
            conflicts=conflicts,
            absents=absents,
            non_recenses=non_recenses,
        )

        if not conflicts:
            embed = discord.Embed(
                title="✅ Aucun conflit de rôle détecté",
                description="Les rôles Discord correspondent au recensement pour les membres analysés.",
                color=discord.Color.green(),
            )
            view._annexes(embed)
            await interaction.followup.send(embed=embed)
            return

        sent = await interaction.followup.send(embed=view.build_current_embed(), view=view, wait=True)
        # On récupère le "vrai" message : ses modifications ne dépendent plus du jeton
        # d'interaction (qui expire après 15 min, trop court pour un gros traitement en lot)
        try:
            view.message = await interaction.channel.fetch_message(sent.id)
        except (discord.HTTPException, AttributeError):
            view.message = sent


async def setup(bot: commands.Bot):
    await bot.add_cog(RecensementSyncCog(bot))