from __future__ import annotations
import os
import asyncio
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
import gspread

from utils import (
    is_user_admin, get_admin_error_embed, get_recensement_worksheet, rename_with_grade,
    ajouter_retrogradation,
)
from data import (
    GRADES_ORDRE, GRADES_META, GRADE_ROLES, SPREADSHEET_ID_DEFAUT,
    COL_DISCORD_ID, COL_NOM_USAGE, COL_GRADE, COL_POINTS,
    LIGNE_DEBUT_DONNEES, LIGNE_FIN_DONNEES,
    cellule, lettre_colonne, rang_grade, requis_defaut, tous_les_roles_grade,
)

# Les tables (grades, rôles...) sont dans data.py

# Grades qu'on peut choisir comme grade d'arrivée : de SDT à l'avant-dernier.
# (Pas EVAT : repasser EVAT reviendrait à annuler la FGI, ce qui se fait à la main.)
GRADES_ARRIVEE = GRADES_ORDRE[1:-1]


def points_apres_retrogradation(nouveau_grade: str) -> str:
    """
    Valeur de la case Points après une rétrogradation.
    Grade aux points : « 0 ». Grade à examen / dossier : case vide, sinon l'ancienne valeur
    serait lue comme « examen validé » et le membre serait repromu à la prochaine vérification.
    """
    try:
        float(requis_defaut(nouveau_grade).replace(",", "."))
        return "0"
    except ValueError:
        return ""


def calculer_retrogradation(grade_actuel: str, grade_demande: str | None) -> tuple[str | None, str | None]:
    """Renvoie (grade d'arrivée, None) ou (None, message d'erreur)."""
    if grade_actuel not in GRADES_ORDRE:
        return None, f"le grade inscrit au recensement (`{grade_actuel or 'vide'}`) est inconnu."
    rang = rang_grade(grade_actuel)
    if grade_demande is None:
        if rang <= 1:
            return None, f"un **{grade_actuel}** ne peut pas être rétrogradé plus bas avec cette commande."
        return GRADES_ORDRE[rang - 1], None
    if grade_demande not in GRADES_ARRIVEE:
        return None, f"`{grade_demande}` n'est pas un grade d'arrivée possible."
    if rang_grade(grade_demande) >= rang:
        return None, (
            f"**{grade_demande}** n'est pas en dessous de son grade actuel (**{grade_actuel}**) : "
            f"ce ne serait pas une rétrogradation."
        )
    return grade_demande, None


class Retrogradation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID") or SPREADSHEET_ID_DEFAUT
        self.credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")
        self.gc = gspread.service_account(filename=self.credentials_path)

    def _retrograder_dans_sheet(self, discord_id: str, grade_demande: str | None) -> tuple[dict | None, str | None]:
        """Trouve la ligne du membre, vérifie la demande et écrit le nouveau grade. (dict, None) ou (None, erreur)."""
        ws = get_recensement_worksheet(self.gc, self.spreadsheet_id)
        derniere = lettre_colonne(max(COL_GRADE, COL_POINTS, COL_NOM_USAGE))
        rows = ws.get(f"A{LIGNE_DEBUT_DONNEES}:{derniere}{LIGNE_FIN_DONNEES}")

        def cell(row: list[str], col: int) -> str:
            return row[col - 1].strip() if len(row) >= col and row[col - 1] else ""

        for ligne, row in enumerate(rows, start=LIGNE_DEBUT_DONNEES):
            if cell(row, COL_DISCORD_ID) != discord_id:
                continue
            grade_actuel = cell(row, COL_GRADE).upper()
            nouveau, erreur = calculer_retrogradation(grade_actuel, grade_demande)
            if erreur:
                return None, erreur
            points = points_apres_retrogradation(nouveau)
            ws.batch_update(
                [
                    {"range": cellule(COL_GRADE, ligne), "values": [[nouveau]]},
                    {"range": cellule(COL_POINTS, ligne), "values": [[points]]},
                ],
                value_input_option="USER_ENTERED",
            )
            return {
                "ligne": ligne,
                "nom_usage": cell(row, COL_NOM_USAGE),
                "old_grade": grade_actuel,
                "new_grade": nouveau,
                "anciens_points": cell(row, COL_POINTS),
                "points": points,
            }, None
        return None, "ce membre est introuvable dans le recensement."

    async def _mettre_a_jour_role(self, membre: discord.Member, nouveau_grade: str, raison: str) -> str:
        """Retire tous les rôles de grade sauf celui du nouveau grade, puis donne celui-ci."""
        cible_id = GRADE_ROLES.get(nouveau_grade)
        role_cible = membre.guild.get_role(cible_id) if cible_id else None
        try:
            a_retirer = [r for r in membre.roles if r.id in tous_les_roles_grade() and r.id != cible_id]
            if a_retirer:
                await membre.remove_roles(*a_retirer, reason=raison)
            if role_cible is None:
                return f"⚠️ Aucun rôle trouvé pour `{nouveau_grade}`"
            if role_cible not in membre.roles:
                await membre.add_roles(role_cible, reason=raison)
            return f"✅ Rôle `{role_cible.name}`"
        except discord.Forbidden:
            return "⚠️ Rôle impossible (hiérarchie bot)"
        except discord.HTTPException as e:
            return f"⚠️ Erreur rôle ({e.status})"

    @app_commands.command(
        name="retrograder",
        description="Rétrograde un membre : recensement, rôle et pseudo, puis annonce à 12h / 19h.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.describe(
        membre="Le membre à rétrograder",
        grade="Grade d'arrivée (par défaut : le grade juste en dessous)",
        raison="Raison (notée dans les logs du serveur, pas dans l'annonce)",
        annoncer="Publier la rétrogradation dans la prochaine annonce de 12h / 19h (par défaut : oui)",
    )
    @app_commands.choices(grade=[
        app_commands.Choice(name=f"{code} — {GRADES_META[code][0]}", value=code) for code in GRADES_ARRIVEE
    ])
    async def retrograder(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        grade: Optional[app_commands.Choice[str]] = None,
        raison: Optional[str] = None,
        annoncer: bool = True,
    ):
        if not is_user_admin(interaction.user):
            await interaction.response.send_message(embed=get_admin_error_embed(), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            resultat, erreur = await asyncio.to_thread(
                self._retrograder_dans_sheet, str(membre.id), grade.value if grade else None
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur Google Sheet : `{e}`", ephemeral=True)
            return
        if erreur:
            await interaction.followup.send(f"❌ Rétrogradation impossible : {erreur}", ephemeral=True)
            return

        old_grade, new_grade = resultat["old_grade"], resultat["new_grade"]
        raison_audit = f"Rétrogradation DMFI : {old_grade} -> {new_grade} par {interaction.user}"
        if raison:
            raison_audit = f"{raison_audit} ({raison})"[:500]

        role_statut = await self._mettre_a_jour_role(membre, new_grade, raison_audit)
        pseudo_statut = await rename_with_grade(membre, new_grade, resultat["nom_usage"], reason=raison_audit)

        annonce_statut = "non publiée (à ta demande)"
        if annoncer:
            try:
                ajouter_retrogradation(str(membre.id), resultat["nom_usage"], old_grade, new_grade)
                annonce_statut = "sera publiée avec la prochaine annonce (12h ou 19h)"
            except OSError as e:
                annonce_statut = f"⚠️ non enregistrée (`{e}`)"

        embed = discord.Embed(
            title="📉 Rétrogradation appliquée",
            description=(
                f"**Membre :** {membre.mention} (ligne `{resultat['ligne']}` du recensement)\n"
                f"**Grade :** `{old_grade}` ➜ **`{new_grade}`**\n"
                f"**Points :** `{resultat['anciens_points'] or 'vide'}` ➜ `{resultat['points'] or 'vide'}`\n"
                f"**Rôle :** {role_statut}\n"
                f"**Pseudo :** {pseudo_statut}\n"
                f"**Annonce :** {annonce_statut}"
                + (f"\n**Raison :** {raison}" if raison else "")
            ),
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Retrogradation(bot))
