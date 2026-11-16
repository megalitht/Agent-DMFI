from __future__ import annotations
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from utils import is_user_admin, get_admin_error_embed
from data import (
    GROUPE_ROLES, GROUPES_AUTO, SERVEUR_PRINCIPAL_ID,
    correction_groupe, grade_le_plus_haut, groupe_grade,
    tous_les_roles_grade, tous_les_roles_groupe,
)

# Les tables (grades, groupes...) sont dans data.py

# Une promotion retire l'ancien rôle de grade PUIS ajoute le nouveau (deux modifications
# séparées). On attend donc quelques secondes après le dernier changement avant de recalculer
# le groupe : sinon le bot verrait un instant le membre « sans grade ».
DELAI_AVANT_CALCUL = 3.0


class GestionRoles(commands.Cog):
    """Rôles de groupe (HDR, SO, OSUB, OSUP, OGEN) alignés automatiquement sur le grade."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._en_attente: dict[tuple[int, int], asyncio.Task] = {}

    async def cog_unload(self):
        for tache in self._en_attente.values():
            tache.cancel()
        self._en_attente.clear()

    # ---------- Cœur : aligner le groupe d'un membre sur son grade ----------

    async def appliquer_groupe(self, membre: discord.Member, raison: str) -> tuple[bool, str | None]:
        """
        Retire les rôles de groupe en trop et donne celui du grade actuel.
        Renvoie (modifié ?, message d'erreur ou None).
        """
        role_ids = {r.id for r in membre.roles}
        a_ajouter, a_retirer = correction_groupe(role_ids)
        if a_ajouter is None and not a_retirer:
            return False, None

        guild = membre.guild
        try:
            if a_retirer:
                roles = [r for r in membre.roles if r.id in a_retirer]
                await membre.remove_roles(*roles, reason=raison)
            if a_ajouter is not None:
                role = guild.get_role(a_ajouter)
                if role is None:
                    return bool(a_retirer), f"rôle de groupe `{a_ajouter}` introuvable sur le serveur"
                await membre.add_roles(role, reason=raison)
            return True, None
        except discord.Forbidden:
            return False, "permission refusée (rôle du bot trop bas dans la hiérarchie ?)"
        except discord.HTTPException as e:
            return False, f"erreur Discord {e.status}"

    # ---------- Automatique : à chaque changement de rôle de grade ----------

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not GROUPES_AUTO or after.bot or not tous_les_roles_groupe():
            return
        if after.guild.id != SERVEUR_PRINCIPAL_ID:
            return

        # On ne réagit qu'aux changements de GRADE : un rôle de groupe donné ou retiré
        # à la main (cas particulier) n'est pas défait.
        ids_grade = tous_les_roles_grade()
        avant = {r.id for r in before.roles} & ids_grade
        apres = {r.id for r in after.roles} & ids_grade
        if avant == apres:
            return

        # Un seul recalcul par membre : chaque nouveau changement relance le délai.
        cle = (after.guild.id, after.id)
        ancienne = self._en_attente.get(cle)
        if ancienne is not None and not ancienne.done():
            ancienne.cancel()
        self._en_attente[cle] = asyncio.create_task(self._recalculer_plus_tard(after.guild, after.id))

    async def _recalculer_plus_tard(self, guild: discord.Guild, membre_id: int):
        cle = (guild.id, membre_id)
        try:
            await asyncio.sleep(DELAI_AVANT_CALCUL)
            membre = guild.get_member(membre_id)  # Version à jour (rôles après tous les changements)
            if membre is None:
                return
            grade = grade_le_plus_haut({r.id for r in membre.roles})
            groupe = groupe_grade(grade) if grade else None
            raison = f"Groupe de grade DMFI : {grade} -> {groupe}" if grade else "Groupe de grade DMFI : plus de grade"
            modifie, erreur = await self.appliquer_groupe(membre, raison)
            if erreur:
                print(f"[GROUPES] {membre} ({membre.id}) : {erreur}")
            elif modifie:
                print(f"[GROUPES] {membre} ({membre.id}) : {grade or 'sans grade'} -> {groupe or 'aucun groupe'}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[GROUPES] Erreur inattendue pour {membre_id} : {e}")
        finally:
            if self._en_attente.get(cle) is asyncio.current_task():
                self._en_attente.pop(cle, None)

    # ---------- Rattrapage : aligner tous les membres déjà gradés ----------

    @app_commands.command(
        name="sync_groupes",
        description="Réaligne les rôles de groupe (HDR, SO, OSUB, OSUP, OGEN) sur le grade de chaque membre.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def sync_groupes(self, interaction: discord.Interaction):
        if not is_user_admin(interaction.user):
            await interaction.response.send_message(embed=get_admin_error_embed(), ephemeral=True)
            return

        guild = interaction.guild
        non_renseignes = [nom for nom, rid in GROUPE_ROLES.items() if rid is None]
        introuvables = [
            nom for nom, rid in GROUPE_ROLES.items() if rid is not None and guild.get_role(rid) is None
        ]
        if not tous_les_roles_groupe():
            await interaction.response.send_message(
                "❌ Aucun rôle de groupe n'est renseigné : complète `GROUPE_ROLES` dans `data.py`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        try:
            if not guild.chunked:
                await guild.chunk()  # Garantit que tous les membres sont en cache
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Impossible de charger la liste des membres : `{e}`")
            return

        ids_grade = tous_les_roles_grade()
        cibles = [m for m in guild.members if not m.bot and ids_grade & {r.id for r in m.roles}]

        envoye = await interaction.followup.send(
            f"⏳ Vérification des groupes de **{len(cibles)}** membre(s) gradé(s)...", wait=True
        )
        # On récupère le "vrai" message : sa modification ne dépend plus du jeton
        # d'interaction (qui expire après 15 min, trop court si beaucoup de rôles sont à corriger)
        try:
            message = await interaction.channel.fetch_message(envoye.id)
        except (discord.HTTPException, AttributeError):
            message = envoye

        corriges = 0
        erreurs: list[str] = []
        for membre in cibles:
            modifie, erreur = await self.appliquer_groupe(membre, f"/sync_groupes par {interaction.user}")
            if erreur:
                erreurs.append(f"• {membre.mention} : {erreur}")
            elif modifie:
                corriges += 1

        embed = discord.Embed(
            title="✅ Groupes de grade réalignés" if not erreurs else "⚠️ Groupes de grade réalignés (avec erreurs)",
            description=(
                f"• **Membres gradés analysés :** `{len(cibles)}`\n"
                f"• **Corrigés :** `{corriges}`\n"
                f"• **Déjà à jour :** `{len(cibles) - corriges - len(erreurs)}`"
            ),
            color=discord.Color.green() if not erreurs else discord.Color.orange(),
        )
        if non_renseignes:
            embed.add_field(
                name="📝 Groupes sans rôle dans data.py (ignorés)",
                value=", ".join(f"`{n}`" for n in non_renseignes), inline=False,
            )
        if introuvables:
            embed.add_field(
                name="❓ Rôles renseignés mais introuvables sur ce serveur",
                value=", ".join(f"`{n}`" for n in introuvables), inline=False,
            )
        if erreurs:
            texte = "\n".join(erreurs[:10])
            if len(erreurs) > 10:
                texte += f"\n… (+{len(erreurs) - 10})"
            embed.add_field(name=f"⚠️ Erreurs ({len(erreurs)})", value=texte[:1020], inline=False)

        try:
            await message.edit(content=None, embed=embed)
        except discord.HTTPException as e:
            print(f"[GROUPES] Impossible d'afficher le résultat de /sync_groupes : {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(GestionRoles(bot))
