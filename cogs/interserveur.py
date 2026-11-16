from __future__ import annotations
import os
import time
import asyncio
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands
import gspread

from utils import is_user_admin, get_admin_error_embed, get_recensement_worksheet
from data import (
    SERVEUR_PRINCIPAL_ID, SERVEURS_LIES, INTERSERVEUR_ACTIF, FILTRAGE_ENTREE,
    EXPULSION_DEPART_PRINCIPAL, EXPULSION_SI_GROUPE_INTERDIT,
    ROLES_MODERATION_PRINCIPAL_IDS, MEMBRES_EXEMPTES_IDS, INTERSERVEUR_LOG_ID,
    MESSAGES_PROMOTION, INVITATION_ENSEIGNEMENT, SPREADSHEET_ID_DEFAUT,
    COL_DISCORD_ID, LIGNE_DEBUT_DONNEES, LIGNE_FIN_DONNEES,
    lettre_colonne, rang_grade, grade_le_plus_haut, groupe_grade,
    sources_membre, sources_valides, groupe_autorise, correction_roles_lies,
)

# Les serveurs, les liaisons de rôles et les textes sont dans data.py (section INTER-SERVEUR)

# Une promotion retire l'ancien rôle PUIS ajoute le nouveau : on attend la fin des changements
# sur le serveur principal avant de les recopier sur les autres serveurs.
DELAI_AVANT_COPIE = 5.0
# Durée pendant laquelle la liste des ID du recensement est gardée en mémoire (secondes)
DUREE_CACHE_RECENSEMENT = 60.0

MOTIF_PAS_PRINCIPAL = "tu n'es pas sur le serveur principal de la DMFI"
MOTIF_PAS_RECENSE = "tu n'es pas inscrit au recensement de la DMFI"
MOTIF_GRADE = "ce serveur est réservé aux sous-officiers et aux officiers"
MOTIF_DEPART = "tu as quitté le serveur principal de la DMFI"


class InterServeur(commands.Cog):
    """Relie les serveurs secondaires au serveur principal : accès, rôles, départs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID") or SPREADSHEET_ID_DEFAUT
        self.credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")
        self.gc = gspread.service_account(filename=self.credentials_path)

        brut = (os.getenv("INTERSERVEUR_LOG_CHANNEL_ID") or "").strip()
        secours = (os.getenv("LOG_RECENSEMENT_CHANNEL_ID") or "").strip()
        self.log_id = int(brut) if brut.isdigit() else (INTERSERVEUR_LOG_ID or (int(secours) if secours.isdigit() else None))

        self._ids_recenses: set[str] = set()
        self._ids_lus_a = 0.0
        self._en_attente: dict[int, asyncio.Task] = {}
        self._sources_avant: dict[int, set[str]] = {}   # Sources au début de la série de changements
        self._dernier_grade: dict[int, str] = {}        # Dernier grade connu (pour repérer une promotion)

    async def cog_load(self):
        # Une faute de frappe dans une source rendrait une liaison muette : on la signale au démarrage
        valides = sources_valides()
        for cfg in SERVEURS_LIES.values():
            for lien in cfg["liens"]:
                for source in lien["sources"] - valides:
                    print(f"[INTER-SERVEUR] ⚠️ Source inconnue « {source} » pour le rôle « {lien['nom']} » ({cfg['nom']})")

    async def cog_unload(self):
        for tache in self._en_attente.values():
            tache.cancel()
        self._en_attente.clear()

    # =================================================================
    # Outils
    # =================================================================

    def principal(self) -> discord.Guild | None:
        return self.bot.get_guild(SERVEUR_PRINCIPAL_ID)

    async def _journal(self, titre: str, description: str, couleur: discord.Color | None = None):
        """Note un événement dans le salon de logs (ou dans la console si aucun salon)."""
        print(f"[INTER-SERVEUR] {titre} — {description}".replace("\n", " | "))
        salon = self.bot.get_channel(self.log_id) if self.log_id else None
        if salon is None:
            return
        embed = discord.Embed(
            title=titre, description=description[:4000],
            color=couleur or discord.Color.dark_grey(), timestamp=datetime.now(),
        )
        try:
            await salon.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as e:
            print(f"[INTER-SERVEUR] Journal non envoyé : {e}")

    def _lire_ids_recenses(self) -> set[str]:
        ws = get_recensement_worksheet(self.gc, self.spreadsheet_id)
        lettre = lettre_colonne(COL_DISCORD_ID)
        valeurs = ws.get(f"{lettre}{LIGNE_DEBUT_DONNEES}:{lettre}{LIGNE_FIN_DONNEES}")
        return {row[0].strip() for row in valeurs if row and row[0].strip().isdigit()}

    async def ids_recenses(self) -> set[str] | None:
        """ID Discord inscrits au recensement. None si le Google Sheet est injoignable."""
        if self._ids_recenses and time.monotonic() - self._ids_lus_a < DUREE_CACHE_RECENSEMENT:
            return self._ids_recenses
        try:
            ids = await asyncio.to_thread(self._lire_ids_recenses)
        except Exception as e:
            print(f"[INTER-SERVEUR] Recensement illisible : {e}")
            return None
        if not ids:
            return None  # Une liste vide est anormale : on ne s'en sert pas pour expulser
        self._ids_recenses, self._ids_lus_a = ids, time.monotonic()
        return ids

    async def membre_principal(self, user_id: int) -> tuple[discord.Member | None, bool]:
        """
        (membre sur le serveur principal ou None, réponse certaine ?).
        Avant de conclure à une absence, on demande confirmation à Discord.
        """
        principal = self.principal()
        if principal is None:
            return None, False
        membre = principal.get_member(user_id)
        if membre is not None:
            return membre, True
        try:
            return await principal.fetch_member(user_id), True
        except discord.NotFound:
            return None, True
        except discord.HTTPException:
            return None, False

    def est_exempte(self, user_id: int, guild: discord.Guild, membre_principal: discord.Member | None) -> bool:
        """Modérateurs et propriétaires : jamais expulsés."""
        if user_id in MEMBRES_EXEMPTES_IDS or user_id == guild.owner_id:
            return True
        if membre_principal is not None:
            return any(r.id in ROLES_MODERATION_PRINCIPAL_IDS for r in membre_principal.roles)
        return False

    async def expulser(self, membre: discord.Member, motif: str, contexte: str) -> bool:
        """Prévient le membre en message privé puis l'expulse du serveur secondaire."""
        guild = membre.guild
        try:
            await membre.send(
                f"❌ Tu ne peux pas rester sur **{guild.name}** : {motif}.\n"
                f"Si c'est une erreur, ouvre un ticket sur le serveur principal."
            )
            mp = "MP envoyé"
        except discord.HTTPException:
            mp = "MP impossible (messages privés fermés)"
        try:
            await membre.kick(reason=f"Agent DMFI — {contexte} : {motif}"[:500])
        except discord.Forbidden:
            await self._journal(
                "⚠️ Expulsion impossible",
                f"**Serveur :** {guild.name}\n**Membre :** {membre.mention} (`{membre}` — `{membre.id}`)\n"
                f"**Motif :** {motif}\nLe bot n'a pas la permission « Expulser des membres » ou son rôle est trop bas.",
                discord.Color.orange(),
            )
            return False
        except discord.HTTPException as e:
            await self._journal("⚠️ Expulsion impossible", f"{guild.name} — {membre} : erreur Discord {e.status}", discord.Color.orange())
            return False
        await self._journal(
            f"🚪 Expulsion — {contexte}",
            f"**Serveur :** {guild.name}\n**Membre :** {membre.mention} (`{membre}` — `{membre.id}`)\n"
            f"**Motif :** {motif}\n**Notification :** {mp}",
            discord.Color.red(),
        )
        return True

    async def appliquer_roles(
        self, membre: discord.Member, sources: set[str], sources_avant: set[str] | None, raison: str
    ) -> tuple[bool, str | None]:
        """Aligne les rôles liés d'un membre sur un serveur secondaire. Renvoie (modifié ?, erreur ou None)."""
        guild = membre.guild
        a_ajouter, a_retirer = correction_roles_lies(guild.id, {r.id for r in membre.roles}, sources, sources_avant)
        if not a_ajouter and not a_retirer:
            return False, None
        introuvables = [rid for rid in a_ajouter if guild.get_role(rid) is None]
        try:
            if a_retirer:
                await membre.remove_roles(*[r for r in membre.roles if r.id in a_retirer], reason=raison)
            roles = [guild.get_role(rid) for rid in a_ajouter if guild.get_role(rid) is not None]
            if roles:
                await membre.add_roles(*roles, reason=raison)
        except discord.Forbidden:
            return False, "permission refusée (rôle du bot trop bas dans la hiérarchie ?)"
        except discord.HTTPException as e:
            return False, f"erreur Discord {e.status}"
        if introuvables:
            return True, "rôle(s) introuvable(s) sur ce serveur : " + ", ".join(f"`{rid}`" for rid in introuvables)
        return True, None

    # =================================================================
    # 1. Arrivée sur un serveur secondaire : filtrage puis rôles
    # =================================================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or member.guild.id not in SERVEURS_LIES:
            return
        guild = member.guild
        principal_membre, certain = await self.membre_principal(member.id)
        exempte = self.est_exempte(member.id, guild, principal_membre)

        if FILTRAGE_ENTREE and not exempte:
            if not certain:
                # Serveur principal injoignable : dans le doute on laisse entrer, et on le signale
                await self._journal(
                    "⚠️ Arrivée non vérifiée",
                    f"**Serveur :** {guild.name}\n**Membre :** {member.mention} (`{member.id}`)\n"
                    f"Le serveur principal n'a pas répondu : la personne est entrée sans contrôle.",
                    discord.Color.orange(),
                )
            elif principal_membre is None:
                await self.expulser(member, MOTIF_PAS_PRINCIPAL, "arrivée refusée")
                return
            else:
                recenses = await self.ids_recenses()
                if recenses is None:
                    await self._journal(
                        "⚠️ Arrivée non vérifiée",
                        f"**Serveur :** {guild.name}\n**Membre :** {member.mention} (`{member.id}`)\n"
                        f"Le recensement (Google Sheet) n'a pas répondu : la personne est entrée sans contrôle.",
                        discord.Color.orange(),
                    )
                elif str(member.id) not in recenses:
                    await self.expulser(member, MOTIF_PAS_RECENSE, "arrivée refusée")
                    return
                grade = grade_le_plus_haut({r.id for r in principal_membre.roles})
                if not groupe_autorise(guild.id, grade):
                    await self.expulser(member, MOTIF_GRADE, "arrivée refusée")
                    return

        if INTERSERVEUR_ACTIF and principal_membre is not None:
            sources = sources_membre({r.id for r in principal_membre.roles})
            _, erreur = await self.appliquer_roles(member, sources, None, "Arrivée : rôles du serveur principal")
            if erreur:
                await self._journal("⚠️ Rôles non attribués à l'arrivée", f"{guild.name} — {member.mention} : {erreur}", discord.Color.orange())

    # =================================================================
    # 2. Changement de rôle sur le principal : copie sur les autres serveurs
    # =================================================================

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.guild.id != SERVEUR_PRINCIPAL_ID or after.bot:
            return
        ids_avant = {r.id for r in before.roles}
        sources_avant = sources_membre(ids_avant)
        if sources_avant == sources_membre({r.id for r in after.roles}):
            return  # Rien qui concerne les autres serveurs

        ancienne = self._en_attente.get(after.id)
        if ancienne is None or ancienne.done():
            # Début d'une série de changements : on retient l'état de départ
            self._sources_avant[after.id] = sources_avant
            grade_avant = grade_le_plus_haut(ids_avant)
            if grade_avant:
                self._dernier_grade[after.id] = grade_avant
        else:
            ancienne.cancel()  # Chaque nouveau changement relance le délai
        self._en_attente[after.id] = asyncio.create_task(self._copier_plus_tard(after.id))

    async def _copier_plus_tard(self, membre_id: int):
        try:
            await asyncio.sleep(DELAI_AVANT_COPIE)
            principal = self.principal()
            membre = principal.get_member(membre_id) if principal else None
            if membre is None:
                return
            sources_avant = self._sources_avant.pop(membre_id, set())
            role_ids = {r.id for r in membre.roles}
            sources = sources_membre(role_ids)
            grade = grade_le_plus_haut(role_ids)

            if INTERSERVEUR_ACTIF:
                await self._copier_sur_les_serveurs(membre, sources, sources_avant, grade)
            await self._message_promotion(membre, grade)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[INTER-SERVEUR] Erreur inattendue pour {membre_id} : {e!r}")
        finally:
            if self._en_attente.get(membre_id) is asyncio.current_task():
                self._en_attente.pop(membre_id, None)

    async def _copier_sur_les_serveurs(
        self, membre: discord.Member, sources: set[str], sources_avant: set[str], grade: str | None
    ):
        for serveur_id in SERVEURS_LIES:
            guild = self.bot.get_guild(serveur_id)
            local = guild.get_member(membre.id) if guild else None
            if local is None:
                continue  # Le bot n'est pas sur ce serveur, ou le membre n'y est pas
            # Un grade connu qui n'a plus accès (ex : sous-officier rétrogradé militaire du rang).
            # « Sans grade » n'expulse jamais : c'est l'état de passage entre deux rôles de grade.
            if (
                EXPULSION_SI_GROUPE_INTERDIT and grade is not None
                and not groupe_autorise(serveur_id, grade)
                and not self.est_exempte(membre.id, guild, membre)
            ):
                await self.expulser(local, MOTIF_GRADE, f"grade {grade} ({groupe_grade(grade)})")
                continue
            _, erreur = await self.appliquer_roles(local, sources, sources_avant, "Copie des rôles du serveur principal")
            if erreur:
                await self._journal("⚠️ Rôles non copiés", f"{guild.name} — {membre.mention} : {erreur}", discord.Color.orange())

    async def _message_promotion(self, membre: discord.Member, grade: str | None):
        """MP de félicitations quand le membre MONTE à un grade de MESSAGES_PROMOTION (SGT, ADJ, SLT...)."""
        ancien = self._dernier_grade.get(membre.id)
        if grade:
            self._dernier_grade[membre.id] = grade
        if not grade or not ancien or grade not in MESSAGES_PROMOTION or rang_grade(grade) <= rang_grade(ancien):
            return
        texte = MESSAGES_PROMOTION[grade].replace("{mention}", membre.mention)
        if INVITATION_ENSEIGNEMENT:
            texte += f"\n\n🔗 **Serveur de l'enseignement :** {INVITATION_ENSEIGNEMENT}"
        else:
            print("[INTER-SERVEUR] INVITATION_ENSEIGNEMENT est vide dans data.py : MP envoyé sans lien.")
        try:
            await membre.send(texte)
        except discord.HTTPException:
            await self._journal(
                "✉️ MP de promotion non remis",
                f"{membre.mention} est passé **{grade}** mais ses messages privés sont fermés.",
            )

    # =================================================================
    # 3. Départ du serveur principal : expulsion des autres serveurs
    # =================================================================

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id != SERVEUR_PRINCIPAL_ID or member.bot or not EXPULSION_DEPART_PRINCIPAL:
            return
        self._dernier_grade.pop(member.id, None)
        self._sources_avant.pop(member.id, None)
        for serveur_id in SERVEURS_LIES:
            guild = self.bot.get_guild(serveur_id)
            local = guild.get_member(member.id) if guild else None
            # `member` garde ses rôles du principal au moment du départ : un modérateur reste exempté
            if local is None or self.est_exempte(member.id, guild, member):
                continue
            await self.expulser(local, MOTIF_DEPART, "départ du serveur principal")

    # =================================================================
    # 4. Rattrapage : /sync_serveurs
    # =================================================================

    @app_commands.command(
        name="sync_serveurs",
        description="Compare les 3 serveurs secondaires au serveur principal (aperçu, ou correction des rôles).",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.describe(
        appliquer="Non (par défaut) : simple aperçu. Oui : corrige les rôles. Personne n'est expulsé par cette commande."
    )
    async def sync_serveurs(self, interaction: discord.Interaction, appliquer: bool = False):
        if not is_user_admin(interaction.user):
            await interaction.response.send_message(embed=get_admin_error_embed(), ephemeral=True)
            return
        principal = self.principal()
        if principal is None:
            await interaction.response.send_message("❌ Le bot ne voit pas le serveur principal.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        envoye = await interaction.followup.send("⏳ Analyse des serveurs en cours...", wait=True)
        # On récupère le "vrai" message : sa modification ne dépend plus du jeton d'interaction (15 min)
        try:
            message = await interaction.channel.fetch_message(envoye.id)
        except (discord.HTTPException, AttributeError):
            message = envoye

        recenses = await self.ids_recenses()
        try:
            if not principal.chunked:
                await principal.chunk()
        except discord.HTTPException:
            pass

        embed = discord.Embed(
            title="🔗 Serveurs secondaires — " + ("rôles corrigés" if appliquer else "aperçu (rien n'a été modifié)"),
            color=discord.Color.green() if appliquer else discord.Color.blurple(),
            timestamp=datetime.now(),
        )
        if recenses is None:
            embed.description = "⚠️ Recensement injoignable : le contrôle « recensé » n'a pas pu être fait."

        for serveur_id, cfg in SERVEURS_LIES.items():
            guild = self.bot.get_guild(serveur_id)
            if guild is None:
                embed.add_field(name=f"❌ {cfg['nom']}", value="Le bot n'est pas sur ce serveur.", inline=False)
                continue
            try:
                if not guild.chunked:
                    await guild.chunk()
            except discord.HTTPException:
                pass

            non_autorises: list[str] = []
            a_corriger = corriges = ajouts = retraits = 0
            erreurs: list[str] = []
            analyses = 0
            for local in guild.members:
                if local.bot:
                    continue
                analyses += 1
                pm = principal.get_member(local.id)
                if not self.est_exempte(local.id, guild, pm):
                    motif = None
                    if pm is None:
                        motif = "absent du principal"
                    elif recenses is not None and str(local.id) not in recenses:
                        motif = "non recensé"
                    elif not groupe_autorise(serveur_id, grade_le_plus_haut({r.id for r in pm.roles})):
                        motif = "grade non autorisé"
                    if motif:
                        non_autorises.append(f"{local.mention} ({motif})")
                        continue
                if pm is None:
                    continue
                sources = sources_membre({r.id for r in pm.roles})
                # sources_avant = sources : les rôles « de départ » ne sont pas redonnés en masse
                plus, moins = correction_roles_lies(serveur_id, {r.id for r in local.roles}, sources, sources)
                if not plus and not moins:
                    continue
                a_corriger += 1
                ajouts += len(plus)
                retraits += len(moins)
                if appliquer:
                    modifie, erreur = await self.appliquer_roles(local, sources, sources, f"/sync_serveurs par {interaction.user}")
                    if erreur:
                        erreurs.append(f"{local.mention} : {erreur}")
                    if modifie:
                        corriges += 1

            sans_id = [l["nom"] for l in cfg["liens"] if l["role_id"] is None]
            introuvables = [l["nom"] for l in cfg["liens"] if l["role_id"] is not None and guild.get_role(l["role_id"]) is None]
            lignes = [
                f"• **Membres analysés :** `{analyses}`",
                (f"• **Membres corrigés :** `{corriges}` / `{a_corriger}`" if appliquer
                 else f"• **Membres à corriger :** `{a_corriger}`") + f" (`+{ajouts}` rôle(s), `-{retraits}` rôle(s))",
            ]
            if non_autorises:
                apercu = ", ".join(non_autorises[:12]) + (f" … (+{len(non_autorises) - 12})" if len(non_autorises) > 12 else "")
                lignes.append(f"• **Ne devraient pas être là ({len(non_autorises)}) :** {apercu}")
            if sans_id:
                lignes.append(f"• **Liaisons sans ID dans data.py (ignorées) :** `{len(sans_id)}` / `{len(cfg['liens'])}`")
            if introuvables:
                lignes.append("• **Rôles introuvables sur ce serveur :** " + ", ".join(f"`{n}`" for n in introuvables[:8]))
            if erreurs:
                lignes.append(f"• **Erreurs ({len(erreurs)}) :** " + " ; ".join(erreurs[:5]))
            embed.add_field(name=f"📍 {cfg['nom']}", value="\n".join(lignes)[:1020], inline=False)

        if not appliquer:
            embed.set_footer(text="Relance avec appliquer:Oui pour corriger les rôles. Les expulsions se font à la main.")
        try:
            await message.edit(content=None, embed=embed)
        except discord.HTTPException as e:
            print(f"[INTER-SERVEUR] Impossible d'afficher le résultat de /sync_serveurs : {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(InterServeur(bot))
