from __future__ import annotations
import os
import json
import asyncio
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands

from utils import admin_only
from data import (
    RECO_FORUM_ID, RECO_LOG_STAFF_ID, RECO_ANONYME, RECO_FICHIER,
    RECO_PANNEAU_FONCTIONNEMENT, RECO_PANNEAU_MODE_EMPLOI,
)

# Les textes du panneau et les réglages sont dans data.py (section RECOMMANDATIONS)


class RecoErreur(Exception):
    """Erreur dont le message peut être affiché tel quel au membre."""


# =====================================================================
# 1. REGISTRE « membre -> son post »
# =====================================================================

class RegistrePosts:
    """
    Retient, pour chaque membre recommandé, l'ID de son post et son nombre de recommandations.
    C'est ce qui permet d'ajouter les recommandations suivantes dans le même post,
    même si le membre change de pseudo. L'auteur d'une recommandation n'y est JAMAIS écrit.
    """

    def __init__(self, chemin: str):
        self.chemin = chemin
        self.fiches: dict[str, dict] = {}
        try:
            with open(chemin, encoding="utf-8") as f:
                contenu = json.load(f)
            if isinstance(contenu, dict):
                self.fiches = contenu
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            # Fichier illisible : on le met de côté au lieu de l'écraser
            print(f"[RECO] Registre illisible ({e}) : mis de côté, un nouveau est créé.")
            try:
                os.replace(chemin, chemin + ".illisible")
            except OSError:
                pass

    def lire(self, membre_id: int) -> dict | None:
        fiche = self.fiches.get(str(membre_id))
        if isinstance(fiche, dict) and isinstance(fiche.get("post"), int):
            return fiche
        return None

    def ecrire(self, membre_id: int, post_id: int, total: int):
        self.fiches[str(membre_id)] = {"post": post_id, "total": total}
        dossier = os.path.dirname(self.chemin)
        if dossier:
            os.makedirs(dossier, exist_ok=True)
        # Écriture dans un fichier temporaire puis remplacement : jamais de fichier à moitié écrit
        temporaire = self.chemin + ".tmp"
        with open(temporaire, "w", encoding="utf-8") as f:
            json.dump(self.fiches, f, indent=2)
        os.replace(temporaire, self.chemin)


# =====================================================================
# 2. INTERFACE
# =====================================================================

# --- Étape 3 : le formulaire (Raison + Avis / Remarques) ---
class RecommandationModal(discord.ui.Modal):
    raison = discord.ui.TextInput(
        label="Raison",
        style=discord.TextStyle.paragraph,
        placeholder="Pourquoi recommandes-tu ce membre ? (comportement, implication, compétences...)",
        required=True,
        max_length=1000,
    )
    avis = discord.ui.TextInput(
        label="Avis / Remarques",
        style=discord.TextStyle.paragraph,
        placeholder="Facultatif : précisions, exemples, contexte...",
        required=False,
        max_length=1000,
    )

    def __init__(self, cog: "Recommandations", cible: discord.Member):
        super().__init__(title=f"Recommander {cible.display_name}"[:45])
        self.cog = cog
        self.cible = cible

    async def on_submit(self, interaction: discord.Interaction):
        # Remplace le menu de sélection (message privé) par un message d'attente
        await interaction.response.edit_message(content="⏳ Publication de ta recommandation...", view=None)
        try:
            message = await self.cog.publier(
                guild=interaction.guild,
                auteur=interaction.user,
                cible=self.cible,
                raison=self.raison.value,
                avis=self.avis.value,
            )
        except RecoErreur as e:
            await interaction.edit_original_response(content=f"❌ {e}")
            return
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="❌ Le bot n'a pas la permission de publier dans le forum des recommandations. "
                        "Contacte un administrateur."
            )
            return
        except discord.HTTPException as e:
            await interaction.edit_original_response(
                content=f"❌ Discord a refusé la publication (erreur {e.status}). Réessaie dans un instant."
            )
            return

        anonymat = " **anonymement**" if RECO_ANONYME else ""
        await interaction.edit_original_response(
            content=f"✅ Ta recommandation pour {self.cible.mention} a été publiée{anonymat} : {message.jump_url}"
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"[RECO] Erreur inattendue : {error!r}")  # L'auteur n'est volontairement pas affiché
        texte = "❌ Une erreur est survenue, ta recommandation n'a pas été publiée."
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(content=texte)
            else:
                await interaction.response.send_message(texte, ephemeral=True)
        except discord.HTTPException:
            pass


# --- Étape 2 : choix du membre recommandé (message visible uniquement par l'auteur) ---
class ChoixMembreView(discord.ui.View):
    def __init__(self, cog: "Recommandations"):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choisis le membre à recommander",
        min_values=1,
        max_values=1,
    )
    async def choisir(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        cible = select.values[0]
        refus = self.cog.motif_refus(interaction.user, cible)
        if refus:
            await interaction.response.send_message(refus, ephemeral=True)
            return
        await interaction.response.send_modal(RecommandationModal(self.cog, cible))


# --- Étape 1 : bouton permanent du panneau ---
class RecommandationLauncherView(discord.ui.View):
    def __init__(self, cog: "Recommandations"):
        super().__init__(timeout=None)  # Permanent même si le bot redémarre
        self.cog = cog

    @discord.ui.button(
        label="Faire une recommandation",
        style=discord.ButtonStyle.success,
        emoji="📨",
        custom_id="dmfi:open_recommandation",
    )
    async def ouvrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.cog.forum(interaction.guild)
        except RecoErreur as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await interaction.response.send_message(
            "**Qui souhaites-tu recommander ?**\nSélectionne le membre dans le menu ci-dessous "
            "(tu peux taper son pseudo pour le chercher).",
            view=ChoixMembreView(self.cog),
            ephemeral=True,
        )


# =====================================================================
# 3. COG
# =====================================================================

def _id_configure(variable_env: str, defaut: int | None) -> int | None:
    """ID lu dans le .env s'il y est, sinon valeur de data.py."""
    brut = (os.getenv(variable_env) or "").strip()
    return int(brut) if brut.isdigit() else defaut


class Recommandations(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.forum_id = _id_configure("RECO_FORUM_CHANNEL_ID", RECO_FORUM_ID)
        self.log_staff_id = _id_configure("RECO_LOG_CHANNEL_ID", RECO_LOG_STAFF_ID)
        self.registre = RegistrePosts(RECO_FICHIER)
        # Une publication à la fois : deux recommandations simultanées pour le même membre
        # ne doivent pas créer deux posts.
        self._verrou = asyncio.Lock()

    async def cog_load(self):
        """Enregistre le bouton permanent au démarrage du Cog."""
        self.bot.add_view(RecommandationLauncherView(self))

    # ---------- Vérifications ----------

    def forum(self, guild: discord.Guild | None) -> discord.ForumChannel:
        """Forum des recommandations sur ce serveur (absent ailleurs que sur le serveur principal)."""
        salon = guild.get_channel(self.forum_id) if (guild and self.forum_id) else None
        if not isinstance(salon, discord.ForumChannel):
            raise RecoErreur(
                "Le forum des recommandations est introuvable sur ce serveur. Contacte un administrateur."
            )
        return salon

    def motif_refus(self, auteur: discord.abc.User, cible: discord.abc.User) -> str | None:
        """Message de refus si cette personne ne peut pas être recommandée, sinon None."""
        if cible.id == auteur.id:
            return "❌ Tu ne peux pas te recommander toi-même. Choisis un autre membre."
        if cible.bot:
            return "❌ Un bot ne peut pas être recommandé. Choisis un autre membre."
        if not isinstance(cible, discord.Member):
            return "❌ Cette personne n'est pas sur le serveur. Choisis un autre membre."
        return None

    # ---------- Publication ----------

    def _embed_recommandation(
        self, auteur: discord.abc.User, cible: discord.Member, raison: str, avis: str, numero: int
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"📨 Recommandation n°{numero}",
            color=discord.Color.gold(),
            timestamp=datetime.now(),
        )
        embed.set_thumbnail(url=cible.display_avatar.url)
        embed.add_field(name="Recommandation de", value=f"{cible.mention} (`{cible.display_name}`)", inline=False)
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.add_field(name="Avis / Remarques", value=avis or "*Aucune remarque*", inline=False)
        embed.add_field(
            name="Recommandation donnée par",
            value="🕶️ Anonyme" if RECO_ANONYME else auteur.mention,
            inline=False,
        )
        return embed

    async def _retrouver_post(
        self, guild: discord.Guild, forum: discord.ForumChannel, fiche: dict | None
    ) -> discord.Thread | None:
        """Post déjà ouvert pour ce membre, ou None s'il n'existe pas / plus."""
        if not fiche:
            return None
        post = guild.get_thread(fiche["post"])
        if post is None:  # Post archivé : absent du cache, on le demande à Discord
            try:
                post = await guild.fetch_channel(fiche["post"])
            except discord.NotFound:
                return None  # Post supprimé : un nouveau sera créé
        if not isinstance(post, discord.Thread) or post.parent_id != forum.id:
            return None
        return post

    async def publier(
        self, guild: discord.Guild, auteur: discord.abc.User, cible: discord.Member, raison: str, avis: str
    ) -> discord.Message:
        """
        Publie la recommandation dans le post du membre (créé s'il n'existe pas encore)
        et renvoie le message publié.
        """
        raison, avis = raison.strip(), (avis or "").strip()
        if not raison:
            raise RecoErreur("La raison ne peut pas être vide.")

        forum = self.forum(guild)
        # Entre le choix du membre et l'envoi du formulaire, la situation a pu changer
        cible = guild.get_member(cible.id)
        if cible is None:
            raise RecoErreur("Ce membre a quitté le serveur entre-temps : rien n'a été publié.")
        refus = self.motif_refus(auteur, cible)
        if refus:
            raise RecoErreur(refus.removeprefix("❌ "))

        nom_post = cible.display_name[:100]
        sans_mention = discord.AllowedMentions.none()

        async with self._verrou:
            fiche = self.registre.lire(cible.id)
            post = await self._retrouver_post(guild, forum, fiche)
            numero = (fiche.get("total", 0) if (fiche and post) else 0) + 1
            embed = self._embed_recommandation(auteur, cible, raison, avis, numero)

            if post is None:
                cree = await forum.create_thread(name=nom_post, embed=embed, allowed_mentions=sans_mention)
                post, message = cree.thread, cree.message
            else:
                if post.archived:
                    await post.edit(archived=False)  # Rouvre le post avant d'y écrire
                message = await post.send(embed=embed, allowed_mentions=sans_mention)
                if post.name != nom_post:
                    # Le pseudo ou le grade a changé : on garde le titre du post à jour
                    try:
                        await post.edit(name=nom_post)
                    except discord.HTTPException:
                        pass

            self.registre.ecrire(cible.id, post.id, numero)

        await self._journal_staff(guild, auteur, cible, message, numero)
        return message

    async def _journal_staff(
        self, guild: discord.Guild, auteur: discord.abc.User, cible: discord.Member,
        message: discord.Message, numero: int,
    ):
        """Note l'auteur dans le salon privé de l'état-major (seulement si un salon est configuré)."""
        salon = guild.get_channel(self.log_staff_id) if self.log_staff_id else None
        if salon is None:
            return
        embed = discord.Embed(
            title="🔒 Recommandation — auteur (confidentiel)",
            description=(
                f"**Auteur :** {auteur.mention} (`{auteur}` — `{auteur.id}`)\n"
                f"**Membre recommandé :** {cible.mention} (`{cible.display_name}`)\n"
                f"**Recommandation n°{numero} :** {message.jump_url}"
            ),
            color=discord.Color.dark_grey(),
            timestamp=datetime.now(),
        )
        try:
            await salon.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as e:
            print(f"[RECO] Journal de l'état-major non envoyé : {e}")

    # ---------- Commande d'installation ----------

    @commands.hybrid_command(
        name="setup_recommandation",
        description="Poste le panneau permanent des recommandations dans ce salon."
    )
    @app_commands.default_permissions(administrator=True)
    @admin_only
    async def setup_recommandation(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("❌ Cette commande s'utilise sur le serveur.", ephemeral=True)
            return

        try:
            forum = self.forum(ctx.guild)
        except RecoErreur:
            await ctx.send(
                "❌ Forum des recommandations introuvable sur ce serveur : renseigne `RECO_FORUM_ID` dans "
                "`data.py` (ou `RECO_FORUM_CHANNEL_ID` dans le `.env`) avec l'ID d'un salon **forum**, "
                "puis redémarre le bot.",
                ephemeral=True,
            )
            return

        fonctionnement = discord.Embed(description=RECO_PANNEAU_FONCTIONNEMENT, color=discord.Color.blue())
        mode_emploi = discord.Embed(
            description=RECO_PANNEAU_MODE_EMPLOI.replace("{forum}", forum.mention),
            color=discord.Color.blue(),
        )
        await ctx.channel.send(embeds=[fonctionnement, mode_emploi], view=RecommandationLauncherView(self))
        await ctx.send("✅ Le panneau des recommandations a été généré.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Recommandations(bot))
