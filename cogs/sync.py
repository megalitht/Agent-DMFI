from __future__ import annotations
import os
import io
import csv
import asyncio
from datetime import datetime
from dataclasses import dataclass
from typing import Literal, Optional
import discord
from discord import app_commands
from discord.ext import commands
import gspread

from utils import (
    is_user_admin, get_admin_error_embed, get_recensement_worksheet, rename_with_grade,
    signaler_suppression_lignes,
)
from data import (
    GRADE_ROLES, SPECIALITE_ROLES, BREVET_ROLES, REGIMENT_ROLES,
    COL_DISCORD_ID, COL_ROBLOX, COL_NOM_USAGE, COL_GRADE, COL_POINTS, COL_REGIMENT, COL_DERNIERE,
    LIGNE_DEBUT_DONNEES, LIGNE_FIN_DONNEES, SPREADSHEET_ID_DEFAUT, SUPPRESSION_AUTO_DEPART,
    cellule, lettre_colonne, rang_grade, tous_les_roles_grade,
)

COCHE = "TRUE (Coché)"
DECOCHE = "FALSE (Décoché)"
AUCUN = "Aucun"
INTROUVABLE = "Introuvable sur le serveur"

TYPE_LABELS = {
    "GRADE": "Grades",
    "SPECIALITE": "Spécialisations",
    "BREVET": "Brevets",
    "REGIMENT": "Régiments",
    "ABSENT": "Absents du Discord",
}


# =====================================================================
# 1. STRUCTURE D'UN CONFLIT
# =====================================================================

@dataclass
class RoleConflict:
    member: Optional[discord.Member]  # None si le joueur n'est plus sur le serveur (ABSENT)
    discord_id: str
    nom_usage: str
    row_number: int      # Ligne actuelle dans le Sheet (recalée si des lignes au-dessus sont supprimées)
    conflict_type: Literal["GRADE", "SPECIALITE", "BREVET", "REGIMENT", "ABSENT"]
    label: str           # Ex: "Grade", "PILOTE", "Régiment", "Joueur absent"
    discord_value: str   # Ex: "CPL", "TRUE (Coché)", "152e RI", "Introuvable sur le serveur"
    sheet_value: str     # Ex: "1CL", "FALSE (Décoché)", "Aucun"
    target_col: int      # Numéro de la colonne à modifier dans Google Sheets
    role_id: int | None = None  # Rôle concerné (spécialisation / brevet)
    original_row: int = 0       # Ligne au moment de l'analyse (pour la sauvegarde CSV)

    def __post_init__(self):
        self.original_row = self.original_row or self.row_number

    def sheet_update(self, vider_si_aucun: bool = False) -> dict | None:
        """
        Cellule à écrire si Discord fait foi. None = rien d'exploitable côté Discord.
        vider_si_aucun : un régiment absent sur Discord met « N/A » dans le Sheet (clic manuel uniquement).
        """
        if self.conflict_type == "ABSENT":
            return None
        if self.conflict_type in ("SPECIALITE", "BREVET"):
            valeur = self.discord_value == COCHE
        else:
            if self.discord_value == AUCUN:
                if vider_si_aucun and self.conflict_type == "REGIMENT":
                    return {"range": cellule(self.target_col, self.row_number), "values": [["N/A"]]}
                return None
            # Plusieurs rôles sur Discord (ex: "CPL, 1CL") : le premier est le plus élevé
            valeur = self.discord_value.split(",")[0].strip()
        return {"range": cellule(self.target_col, self.row_number), "values": [[valeur]]}


def compute_conflicts(
    rows: list[list[str]],
    guild: discord.Guild,
    categorie: str = "ALL",
    only_member_id: int | None = None,
) -> tuple[list[RoleConflict], list[discord.Member]]:
    """
    Compare le recensement aux rôles Discord.
    `rows` commence à la ligne LIGNE_DEBUT_DONNEES du Sheet.
    Renvoie (conflits [dont les joueurs absents du Discord], membres gradés non recensés).
    """
    id_to_grade = {rid: code for code, rid in GRADE_ROLES.items() if rid is not None}
    id_to_regiment = {rid: name for name, rid in REGIMENT_ROLES.items() if rid is not None}

    conflicts: list[RoleConflict] = []
    ids_recenses: set[int] = set()

    def cell(row: list[str], col: int) -> str:
        return row[col - 1].strip() if len(row) >= col and row[col - 1] else ""

    def veut(type_: str) -> bool:
        return categorie in ("ALL", type_)

    for row_number, row in enumerate(rows, start=LIGNE_DEBUT_DONNEES):
        raw_id = cell(row, COL_DISCORD_ID)
        if not raw_id.isdigit():
            continue  # Ligne vide ou sans ID Discord : jamais touchée

        discord_id = int(raw_id)
        ids_recenses.add(discord_id)
        if only_member_id is not None and discord_id != only_member_id:
            continue

        nom_usage = cell(row, COL_NOM_USAGE)
        member = guild.get_member(discord_id)

        # --- 0. JOUEUR ABSENT DU DISCORD ---
        if member is None:
            if veut("ABSENT"):
                conflicts.append(RoleConflict(
                    member=None, discord_id=raw_id,
                    nom_usage=nom_usage or cell(row, COL_ROBLOX) or raw_id,
                    row_number=row_number, conflict_type="ABSENT", label="Joueur absent",
                    discord_value=INTROUVABLE,
                    sheet_value=f"{cell(row, COL_GRADE) or '?'} — Roblox : {cell(row, COL_ROBLOX) or '?'}",
                    target_col=COL_DISCORD_ID,
                ))
            continue

        nom_usage = nom_usage or member.display_name
        member_role_ids = {r.id for r in member.roles}
        base = dict(member=member, discord_id=raw_id, nom_usage=nom_usage, row_number=row_number)

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

    return conflicts, non_recenses


def delete_sheet_row(worksheet: gspread.Worksheet, row_number: int, expected_id: str) -> tuple[list[str], list[str]]:
    """
    Supprime la ligne `row_number` après avoir vérifié qu'elle contient bien `expected_id` en colonne A.
    Renvoie (en-têtes, valeurs de la ligne supprimée) pour la sauvegarde.
    """
    derniere = lettre_colonne(COL_DERNIERE)
    ligne_entete = LIGNE_DEBUT_DONNEES - 1
    header_range, row_range = worksheet.batch_get([
        f"A{ligne_entete}:{derniere}{ligne_entete}",
        f"A{row_number}:{derniere}{row_number}",
    ])
    header = list(header_range[0]) if header_range else []
    values = list(row_range[0]) if row_range else []

    if not header or header[0].strip().lower() != "id discord":
        raise RuntimeError("l'onglet ouvert ne ressemble pas au recensement (A2 ≠ « ID Discord »)")
    if not values or values[0].strip() != expected_id:
        raise RuntimeError(f"la ligne {row_number} a changé depuis l'analyse : relance /sync")

    worksheet.delete_rows(row_number)
    return header, values


def delete_rows_for_id(worksheet: gspread.Worksheet, discord_id: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """
    Supprime toutes les lignes dont l'ID Discord (colonne A) vaut `discord_id`.
    Renvoie (en-têtes, [(numéro de ligne, valeurs)]) pour la sauvegarde.
    """
    plage = f"A{LIGNE_DEBUT_DONNEES - 1}:{lettre_colonne(COL_DERNIERE)}{LIGNE_FIN_DONNEES}"
    data = worksheet.get(plage)
    header = list(data[0]) if data else []
    if not header or header[0].strip().lower() != "id discord":
        raise RuntimeError("l'onglet ouvert ne ressemble pas au recensement (A2 ≠ « ID Discord »)")

    cibles = [
        (row_number, list(row))
        for row_number, row in enumerate(data[1:], start=LIGNE_DEBUT_DONNEES)
        if row and row[0].strip() == discord_id
    ]
    if cibles:
        # Une seule requête, du bas vers le haut pour que les numéros restent valides
        worksheet.spreadsheet.batch_update({"requests": [
            {"deleteDimension": {"range": {
                "sheetId": worksheet.id, "dimension": "ROWS",
                "startIndex": n - 1, "endIndex": n,
            }}}
            for n, _ in sorted(cibles, key=lambda x: x[0], reverse=True)
        ]})
    return header, cibles


def backup_csv(header: list[str], lignes: list[tuple[int, list[str]]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Ligne d'origine"] + header)
    for ligne, values in lignes:
        writer.writerow([ligne] + values)
    return buf.getvalue().encode("utf-8-sig")


# Fenêtres /sync ouvertes : elles doivent recaler leurs numéros de ligne à chaque suppression
_VUES_SYNC_ACTIVES: set["ConflictResolutionView"] = set()


async def signaler_lignes_supprimees(lignes: list[int], source: "ConflictResolutionView | None" = None):
    """
    À appeler après chaque suppression de ligne (bouton 🗑️ ou départ d'un membre).
    Recale toutes les fenêtres /sync ouvertes et bloque les autres fenêtres de confirmation.
    """
    signaler_suppression_lignes()
    for vue in list(_VUES_SYNC_ACTIVES):
        affiche_avant = vue.current
        vue._appliquer_suppressions(lignes)
        # Si le conflit affiché a disparu (sa ligne vient d'être supprimée), on met l'embed à jour
        if vue is not source and vue.current is not affiche_avant:
            await vue._refresh()


# =====================================================================
# 2. INTERFACE INTERACTIVE (BOUTONS)
# =====================================================================

class ConflictResolutionView(discord.ui.View):
    def __init__(
        self,
        author: discord.abc.User,
        worksheet: gspread.Worksheet,
        conflicts: list[RoleConflict],
        non_recenses: list[discord.Member],
        member_list_complete: bool = True,
    ):
        super().__init__(timeout=900)  # Expire au bout de 15 minutes d'inactivité
        self.author = author
        self.worksheet = worksheet
        self.conflicts = conflicts
        self.non_recenses = non_recenses
        self.member_list_complete = member_list_complete
        self.message: discord.Message | None = None
        self.initial_total = len(conflicts)
        self.current_index = 0
        self.resolved_count = 0
        self.deleted_rows: list[tuple[int, list[str]]] = []  # (ligne d'origine, valeurs)
        self.header: list[str] = []
        self.backup_sent = False
        self.errors: list[str] = []
        self.busy = False
        self.pending_delete: RoleConflict | None = None  # Confirmation en 2 clics pour un membre présent
        self._update_buttons()
        _VUES_SYNC_ACTIVES.add(self)

    def stop(self):
        _VUES_SYNC_ACTIVES.discard(self)
        super().stop()

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
        _VUES_SYNC_ACTIVES.discard(self)
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass
        await self._send_backup()

    # ---------- État ----------

    @property
    def current(self) -> RoleConflict | None:
        return self.conflicts[self.current_index] if self.current_index < len(self.conflicts) else None

    def _update_buttons(self):
        """Active le bon jeu de boutons selon le type du conflit affiché."""
        c = self.current
        absent = c is not None and c.conflict_type == "ABSENT"
        self.validate_discord.disabled = absent
        self.validate_sheets.disabled = absent
        self.delete_row.disabled = c is None
        if c is not None and c is self.pending_delete:
            self.delete_row.label = "Confirmer : supprimer la ligne ?"
        else:
            self.delete_row.label = "Supprimer la ligne Sheet"

    # ---------- Embeds ----------

    def _resume_par_type(self, conflicts: list[RoleConflict]) -> str:
        compte: dict[str, int] = {}
        for c in conflicts:
            compte[c.conflict_type] = compte.get(c.conflict_type, 0) + 1
        return " • ".join(f"{TYPE_LABELS[t]} : `{n}`" for t, n in compte.items()) or "*Aucun*"

    def _annexes(self, embed: discord.Embed):
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
        if progress:
            return discord.Embed(title="⏳ Synchronisation en cours...", description=progress, color=discord.Color.blurple())

        c = self.current
        if c is None:
            nb_suppr = len(self.deleted_rows)
            embed = discord.Embed(
                title="✅ Synchronisation DMFI terminée",
                description=(
                    f"• **Corrections appliquées :** `{self.resolved_count}`\n"
                    f"• **Lignes supprimées (joueurs absents) :** `{nb_suppr}`\n"
                    f"• **Ignorés :** `{max(0, self.initial_total - self.resolved_count - nb_suppr)}`"
                ),
                color=discord.Color.green() if not self.errors else discord.Color.orange(),
            )
            self._annexes(embed)
            return embed

        total = len(self.conflicts)
        if c.conflict_type == "ABSENT":
            joueur = f"<@{c.discord_id}> (`{c.discord_id}`)"
            titre = f"👻 Joueur introuvable sur le Discord ({self.current_index + 1}/{total})"
        else:
            joueur = f"{c.member.mention} (`{c.member.name}`)"
            titre = f"⚠️ Conflit détecté ({self.current_index + 1}/{total})"

        embed = discord.Embed(
            title=titre,
            description=(
                f"**Joueur :** {joueur}\n"
                f"**Nom d'usage (Sheet) :** `{c.nom_usage}`\n"
                f"**Ligne Google Sheets :** `{c.row_number}`\n"
                f"**Type de conflit :** `{c.label}`"
            ),
            color=discord.Color.dark_grey() if c.conflict_type == "ABSENT" else discord.Color.orange(),
        )
        embed.add_field(name="🔵 Sur Discord", value=f"**`{c.discord_value}`**", inline=True)
        embed.add_field(name="🟢 Sur Google Sheets", value=f"**`{c.sheet_value}`**", inline=True)
        embed.add_field(
            name=f"📊 Restant ({total - self.current_index})",
            value=self._resume_par_type(self.conflicts[self.current_index:]),
            inline=False,
        )
        self._annexes(embed)
        if c.conflict_type == "ABSENT":
            embed.set_footer(text="🗑️ supprime la ligne du Google Sheet (sauvegarde CSV postée à la fin) • ⏭️ la conserve.")
        else:
            embed.set_footer(text="🗑️ supprime toute la ligne du joueur (2 clics s'il est encore sur le serveur) • Les boutons « Tout » ne suppriment jamais de ligne.")
        return embed

    async def _refresh(self, progress: str | None = None):
        finished = self.current is None
        if finished and not progress:
            self.stop()
        self._update_buttons()
        view = None if (finished or progress) else self
        if self.message:
            try:
                await self.message.edit(embed=self.build_current_embed(progress), view=view)
            except discord.HTTPException as e:
                print(f"[SYNC] Impossible de mettre à jour le message : {e}")
        if finished and not progress:
            await self._send_backup()

    async def _send_backup(self):
        """Poste une seule fois la sauvegarde CSV des lignes supprimées."""
        if self.backup_sent or not self.deleted_rows or not self.message:
            return
        self.backup_sent = True
        contenu = backup_csv(self.header, self.deleted_rows)
        nom = f"recensement_supprimes_{datetime.now().strftime('%Y-%m-%d_%Hh%M')}.csv"
        try:
            await self.message.channel.send(
                f"💾 Sauvegarde des **{len(self.deleted_rows)}** ligne(s) supprimée(s) du recensement "
                f"(s'ouvre dans Excel / Google Sheets, à garder en cas d'erreur) :",
                file=discord.File(io.BytesIO(contenu), filename=nom),
            )
        except discord.HTTPException as e:
            print(f"[SYNC] Sauvegarde CSV non envoyée : {e}")

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

    def _appliquer_suppressions(self, lignes: list[int]):
        """
        Des lignes ont été supprimées du Sheet : les conflits restants sur ces lignes disparaissent
        et ceux situés en dessous remontent d'un cran (sinon on écrirait sur le mauvais joueur).
        """
        for r in sorted(lignes, reverse=True):
            restants = []
            for c in self.conflicts[self.current_index:]:
                if c.row_number == r:
                    continue
                if c.row_number > r:
                    c.row_number -= 1
                restants.append(c)
            self.conflicts = self.conflicts[:self.current_index] + restants

    def _keep_only_absents_after_current(self):
        """Après un traitement en lot, il ne reste à passer en revue que les joueurs absents."""
        self.conflicts = self.conflicts[:self.current_index] + [
            c for c in self.conflicts[self.current_index:] if c.conflict_type == "ABSENT"
        ]

    # ---------- Boutons : un conflit à la fois ----------

    @discord.ui.button(label="Discord est valide (Maj Sheet)", style=discord.ButtonStyle.primary, emoji="🔵", row=0)
    async def validate_discord(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        c = self.current
        update = c.sheet_update(vider_si_aucun=True)
        if update is None:
            await interaction.followup.send(
                "⚠️ Ce membre n'a aucun grade sur Discord : je ne vide pas la case Grade du Sheet. "
                "Utilise 🟢 pour lui donner le rôle, 🗑️ pour supprimer sa ligne, ou ⏭️ pour ignorer.",
                ephemeral=True,
            )
            return
        try:
            await asyncio.to_thread(self.worksheet.batch_update, [update], value_input_option="USER_ENTERED")
            self.resolved_count += 1
        except Exception as e:
            self.errors.append(f"• Écriture Google Sheets impossible : `{e}`")
        self.current_index += 1
        await self._refresh()

    @discord.ui.button(label="Google Sheets est valide (Maj Discord)", style=discord.ButtonStyle.success, emoji="🟢", row=0)
    async def validate_sheets(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if await self._apply_sheet_to_discord(self.current):
            self.resolved_count += 1
        self.current_index += 1
        await self._refresh()

    @discord.ui.button(label="Supprimer la ligne Sheet", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def delete_row(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        c = self.current
        if c is None:
            return

        if c.conflict_type == "ABSENT":
            # Garde-fous : liste des membres complète + joueur toujours absent
            if not self.member_list_complete:
                await interaction.followup.send(
                    "❌ Le bot ne voit pas tous les membres du serveur (intent **Server Members** ?) : "
                    "suppression bloquée pour ne pas effacer un joueur encore présent.",
                    ephemeral=True,
                )
                return
            if interaction.guild and interaction.guild.get_member(int(c.discord_id)) is not None:
                await interaction.followup.send("ℹ️ Ce joueur est revenu sur le serveur : ligne conservée.", ephemeral=True)
                self.current_index += 1
                await self._refresh()
                return
        elif self.pending_delete is not c:
            # Membre encore présent sur le serveur : on demande un 2e clic pour confirmer
            self.pending_delete = c
            await self._refresh()
            await interaction.followup.send(
                f"⚠️ **{c.nom_usage}** est toujours sur le serveur. Reclique sur 🗑️ pour supprimer "
                f"sa ligne {c.row_number} du recensement (grade, points et brevets compris).",
                ephemeral=True,
            )
            return

        self.pending_delete = None
        self.busy = True
        try:
            header, values = await asyncio.to_thread(delete_sheet_row, self.worksheet, c.row_number, c.discord_id)
        except Exception as e:
            await interaction.followup.send(f"❌ Ligne non supprimée : `{e}`", ephemeral=True)
            await self._refresh()
            return
        finally:
            self.busy = False

        self.header = header
        self.deleted_rows.append((c.original_row, values))
        # Retire tous les conflits de cette ligne (y compris celui affiché) et recale les suivants,
        # ici et dans les autres fenêtres /sync ouvertes
        await signaler_lignes_supprimees([c.row_number], source=self)
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
            restants = [c for c in self.conflicts[self.current_index:] if c.conflict_type != "ABSENT"]
            for i, c in enumerate(restants, start=1):
                # Un grade vide dans le Sheet ne retire pas les rôles en masse : à traiter à la main
                if c.conflict_type in ("GRADE", "REGIMENT") and c.sheet_value == AUCUN:
                    continue
                if await self._apply_sheet_to_discord(c):
                    self.resolved_count += 1
                if i % 10 == 0:
                    await self._refresh(progress=f"Mise à jour des rôles Discord : `{i}/{len(restants)}`")
            self._keep_only_absents_after_current()
        finally:
            self.busy = False
        await self._refresh()

    @discord.ui.button(label="Tout : Discord ➜ Sheet", style=discord.ButtonStyle.primary, emoji="⏩", row=1)
    async def all_discord(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.busy = True
        try:
            # Les membres sans rôle sur Discord et les absents sont ignorés (on ne vide pas le Sheet en masse)
            self.resolved_count += await self._apply_discord_to_sheet(self.conflicts[self.current_index:])
            self._keep_only_absents_after_current()
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

    # ---------- Départ d'un membre : suppression automatique de sa ligne ----------

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot or not SUPPRESSION_AUTO_DEPART:
            return
        try:
            ws = await asyncio.to_thread(get_recensement_worksheet, self.gc, self.spreadsheet_id)
            header, lignes = await asyncio.to_thread(delete_rows_for_id, ws, str(member.id))
        except Exception as e:
            print(f"[SYNC] Départ de {member} ({member.id}) : suppression impossible : {e}")
            await self._log_depart(member, [], [], erreur=str(e))
            return
        if not lignes:
            return  # Pas recensé : rien à faire

        await signaler_lignes_supprimees([n for n, _ in lignes])
        print(f"[SYNC] Départ de {member} ({member.id}) : ligne(s) {[n for n, _ in lignes]} supprimée(s).")
        await self._log_depart(member, header, lignes)

    async def _log_depart(self, member: discord.Member, header: list[str], lignes: list[tuple[int, list[str]]], erreur: str | None = None):
        """Poste le récapitulatif + la sauvegarde CSV dans le salon de logs du recensement."""
        salon_id = os.getenv("LOG_RECENSEMENT_CHANNEL_ID", "")
        salon = self.bot.get_channel(int(salon_id)) if salon_id.isdigit() else None
        if salon is None:
            return

        if erreur:
            embed = discord.Embed(
                title="⚠️ Départ du serveur — ligne NON supprimée",
                description=f"**Membre :** {member.mention} (`{member}` — `{member.id}`)\n**Erreur :** `{erreur}`\n"
                            f"Sa ligne est restée dans le recensement : `/sync` permettra de la supprimer.",
                color=discord.Color.orange(), timestamp=datetime.now(),
            )
            await salon.send(embed=embed)
            return

        def val(row: list[str], col: int) -> str:
            return row[col - 1].strip() if len(row) >= col and row[col - 1] else "—"

        n, row = lignes[0]
        diplomes = [
            code for code, cfg in {**SPECIALITE_ROLES, **BREVET_ROLES}.items()
            if val(row, cfg["col_index"]).upper() == "TRUE"
        ]
        embed = discord.Embed(
            title="📤 Départ du serveur — ligne supprimée du recensement",
            description=(
                f"**Membre :** {member.mention} (`{member}` — `{member.id}`)\n"
                f"**Nom d'usage :** `{val(row, COL_NOM_USAGE)}` • **Roblox :** `{val(row, COL_ROBLOX)}`\n"
                f"**Grade :** `{val(row, COL_GRADE)}` • **Points :** `{val(row, COL_POINTS)}` • "
                f"**Régiment :** `{val(row, COL_REGIMENT)}`\n"
                f"**Spécialités / brevets :** {', '.join(f'`{d}`' for d in diplomes) or '*aucun*'}\n"
                f"**Ligne(s) supprimée(s) :** {', '.join(f'`{num}`' for num, _ in lignes)}"
            ),
            color=discord.Color.dark_grey(), timestamp=datetime.now(),
        )
        embed.set_footer(text="Sauvegarde CSV jointe : de quoi recréer sa ligne s'il revient.")
        try:
            await salon.send(
                embed=embed,
                file=discord.File(io.BytesIO(backup_csv(header, lignes)), filename=f"depart_{member.id}.csv"),
            )
        except discord.HTTPException as e:
            print(f"[SYNC] Log de départ non envoyé : {e}")

    @app_commands.command(name="sync", description="Détecte et corrige les écarts entre le Discord et le recensement.")
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
        app_commands.Choice(name="Joueurs absents du Discord", value="ABSENT"),
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

        conflicts, non_recenses = compute_conflicts(
            rows, guild,
            categorie=categorie.value if categorie else "ALL",
            only_member_id=membre.id if membre else None,
        )

        # Si le bot ne voit pas tous les membres, les "absents" ne sont pas fiables : suppression bloquée
        member_list_complete = not (guild.member_count and len(guild.members) < guild.member_count)

        view = ConflictResolutionView(
            author=interaction.user,
            worksheet=worksheet,
            conflicts=conflicts,
            non_recenses=non_recenses,
            member_list_complete=member_list_complete,
        )

        if not conflicts:
            embed = discord.Embed(
                title="✅ Aucun conflit détecté",
                description="Le Discord correspond au recensement pour les membres analysés.",
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
