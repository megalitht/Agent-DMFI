from __future__ import annotations
import os
import asyncio
from datetime import datetime
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
import gspread

from utils import (
    is_user_admin, is_formateur_or_admin, get_admin_error_embed,
    get_recensement_worksheet, find_player, split_pseudos,
)
from data import (
    COL_DERNIERE, LIGNE_DEBUT_DONNEES, LIGNE_FIN_DONNEES, SPREADSHEET_ID_DEFAUT,
    cellule, lettre_colonne, get_diplome, tous_les_diplomes,
)

TYPE_LABELS = {"SPECIALITE": "Spécialisation", "BREVET": "Brevet"}


# --- 1. POP-UP POUR AJOUTER / RETIRER DES MEMBRES AVANT VALIDATION ---
class ModifierDiplomeModal(discord.ui.Modal, title="Modifier la liste"):
    ajouter = discord.ui.TextInput(
        label="Ajouter (Roblox, nom d'usage ou ID Discord)",
        placeholder="Sépare par une virgule ou un espace",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    retirer = discord.ui.TextInput(
        label="Retirer de la liste",
        placeholder="Sépare par une virgule ou un espace",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    notes = discord.ui.TextInput(
        label="Notes / Observations",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, view: "DiplomeConfirmView"):
        super().__init__()
        self.dip_view = view
        self.notes.default = view.notes

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        for token in split_pseudos(self.ajouter.value):
            self.dip_view.add_name(token, manual=True)
        for token in split_pseudos(self.retirer.value):
            self.dip_view.remove_name(token)
        self.dip_view.notes = self.notes.value.strip()

        await self.dip_view.message.edit(embed=self.dip_view.build_preview_embed(), view=self.dip_view)
        await interaction.followup.send("✅ Liste mise à jour.", ephemeral=True)


# --- 2. VUE DE CONFIRMATION ---
class DiplomeConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "Diplomes",
        author: discord.Member,
        diplome: dict,
        retrait: bool,
        sheet_index: list[dict],
        detected_raw: list[str],
        manual_raw: list[str],
        image_url: str | None,
        notes: str = "",
    ):
        super().__init__(timeout=900)
        self.cog = cog
        self.author = author
        self.diplome = diplome      # {"code", "type", "role_id", "col_index"}
        self.retrait = retrait
        self.sheet_index = sheet_index
        self.image_url = image_url
        self.notes = notes
        self.message: discord.Message | None = None

        self.to_update: dict[int, dict] = {}   # Membres dont la case va changer
        self.unchanged: dict[int, dict] = {}   # Déjà titulaires (ou déjà sans le diplôme en mode retrait)
        self.excluded: dict[int, dict] = {}    # Le formateur lui-même, vu sur la capture
        self.unmatched: list[str] = []

        for name in manual_raw:
            self.add_name(name, manual=True)
        for name in detected_raw:
            self.add_name(name, manual=False)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        autorise = is_user_admin(interaction.user) if self.retrait else is_formateur_or_admin(interaction.user)
        if not autorise:
            await interaction.response.send_message(embed=get_admin_error_embed(), ephemeral=True)
            return False
        return True

    def add_name(self, name: str, manual: bool):
        self.unmatched = [u for u in self.unmatched if u.lower() != name.lower()]
        entry = find_player(self.sheet_index, name, allow_discord=manual)
        if not entry:
            if name not in self.unmatched:
                self.unmatched.append(name)
            return

        row = entry["row"]
        if row in self.to_update or row in self.unchanged:
            return
        # Le formateur apparaît sur sa propre capture : on ne lui donne pas le diplôme par OCR
        if not manual and entry["discord_id"] == str(self.author.id):
            self.excluded[row] = entry
            return
        self.excluded.pop(row, None)

        if entry["has_diplome"] == (not self.retrait):
            self.unchanged[row] = entry
        else:
            self.to_update[row] = entry

    def remove_name(self, name: str):
        q = name.strip().lower().strip("<@!>")
        self.unmatched = [u for u in self.unmatched if u.lower() != name.strip().lower()]
        for d in (self.to_update, self.unchanged, self.excluded):
            for row in list(d.keys()):
                p = d[row]
                if q in {p["roblox"].lower(), p["nom_usage"].lower(), p["discord_tag"].lower(), p["discord_id"]}:
                    del d[row]

    @staticmethod
    def _liste(players: dict[int, dict]) -> str:
        texte = "\n".join(
            f"• **{p['nom_usage']}** (`{p['roblox']}` — {p['grade']})" for p in players.values()
        )
        return texte if len(texte) <= 1020 else texte[:1015] + "\n..."

    def build_preview_embed(self, finalized: bool = False, bilan: str | None = None) -> discord.Embed:
        d = self.diplome
        genre = TYPE_LABELS[d["type"]]
        verbe = "Retrait" if self.retrait else "Attribution"
        if finalized:
            title, color = f"✅ {verbe} validé — {genre} {d['code']}", discord.Color.green()
        else:
            title, color = f"🎓 {verbe} — {genre} {d['code']} (En attente de confirmation)", discord.Color.orange()

        role_txt = f"<@&{d['role_id']}>" if d["role_id"] else "*aucun rôle configuré dans data.py (Sheet uniquement)*"
        embed = discord.Embed(
            title=title,
            description=(
                f"**Formateur :** {self.author.mention}\n"
                f"**{genre} :** `{d['code']}` (colonne `{lettre_colonne(d['col_index'])}` du recensement)\n"
                f"**Rôle Discord :** {role_txt}"
            ),
            color=color,
            timestamp=datetime.now()
        )
        if self.image_url:
            embed.set_thumbnail(url=self.image_url)

        action = "Diplôme retiré" if self.retrait else "Diplômés"
        embed.add_field(
            name=f"{'➖' if self.retrait else '✅'} {action} ({len(self.to_update)})",
            value=self._liste(self.to_update) or "*Aucun membre à mettre à jour.*",
            inline=False
        )
        if self.unchanged:
            embed.add_field(
                name=f"ℹ️ {'Ne l’avaient pas' if self.retrait else 'Déjà titulaires'} ({len(self.unchanged)})",
                value=self._liste(self.unchanged),
                inline=False
            )
        if self.excluded:
            embed.add_field(
                name="🎖️ Formateur présent sur la capture (non diplômé)",
                value=self._liste(self.excluded),
                inline=False
            )
        if self.unmatched:
            embed.add_field(
                name=f"⚠️ Pseudos non trouvés sur le Sheet ({len(self.unmatched)})",
                value=", ".join(f"`{u}`" for u in self.unmatched)[:1020],
                inline=False
            )
        if self.notes:
            embed.add_field(name="📝 Notes / Observations", value=f"> {self.notes}", inline=False)
        if bilan:
            embed.add_field(name="📌 Bilan", value=bilan, inline=False)

        embed.set_footer(
            text="Google Sheet mis à jour avec succès."
            if finalized else "Vérifie la liste puis clique sur Confirmer ou Modifier."
        )
        return embed

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.to_update:
            await interaction.response.send_message("⚠️ Aucun membre à mettre à jour dans la liste actuelle.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        d = self.diplome

        # 1. Google Sheet (une seule requête)
        try:
            await asyncio.to_thread(
                self.cog._apply_diplome_batch, list(self.to_update.keys()), d["col_index"], not self.retrait
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la mise à jour Google Sheet : `{e}`", ephemeral=True)
            return

        # 2. Rôles Discord
        guild = interaction.guild
        role = guild.get_role(d["role_id"]) if (guild and d["role_id"]) else None
        nb_roles, echecs = 0, []
        if role:
            raison = f"{'Retrait' if self.retrait else 'Attribution'} {d['code']} par {interaction.user}"
            for p in self.to_update.values():
                membre = None
                if p["discord_id"].isdigit():
                    membre = guild.get_member(int(p["discord_id"]))
                    if membre is None:
                        try:
                            membre = await guild.fetch_member(int(p["discord_id"]))
                        except discord.HTTPException:
                            membre = None
                if membre is None:
                    echecs.append(f"{p['nom_usage']} (absent du serveur)")
                    continue
                try:
                    if self.retrait:
                        await membre.remove_roles(role, reason=raison)
                    else:
                        await membre.add_roles(role, reason=raison)
                    nb_roles += 1
                except discord.Forbidden:
                    echecs.append(f"{p['nom_usage']} (hiérarchie du bot)")
                except discord.HTTPException as e:
                    echecs.append(f"{p['nom_usage']} (erreur {e.status})")

        bilan = f"• Sheet : **{len(self.to_update)}** case(s) {'décochée(s)' if self.retrait else 'cochée(s)'}\n"
        if role:
            bilan += f"• Rôle {role.mention} : **{nb_roles}** membre(s) mis à jour"
        elif d["role_id"]:
            bilan += f"• ⚠️ Rôle `{d['role_id']}` introuvable sur le serveur"
        else:
            bilan += "• Aucun rôle Discord configuré pour ce diplôme"
        if echecs:
            bilan += "\n• ⚠️ Échecs rôle : " + ", ".join(echecs)

        self.stop()
        await interaction.message.edit(embed=self.build_preview_embed(finalized=True, bilan=bilan[:1020]), view=None)
        await interaction.followup.send("✅ Validé.", ephemeral=True)

    @discord.ui.button(label="Ajouter / Retirer", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModifierDiplomeModal(self))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        embed.title = "❌ Demande annulée"
        embed.color = discord.Color.red()
        self.stop()
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("🛑 Annulé, rien n'a été modifié.", ephemeral=True)


# --- 3. COG ---
class Diplomes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID") or SPREADSHEET_ID_DEFAUT
        self.credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")
        self.gc = gspread.service_account(filename=self.credentials_path)

    def _fetch_sheet_index(self, col_index: int) -> list[dict]:
        """Index des membres + état actuel de la case du diplôme demandé."""
        ws = get_recensement_worksheet(self.gc, self.spreadsheet_id)
        rows = ws.get(f"A{LIGNE_DEBUT_DONNEES}:{lettre_colonne(COL_DERNIERE)}{LIGNE_FIN_DONNEES}")

        index_list = []
        for idx, row in enumerate(rows, start=LIGNE_DEBUT_DONNEES):
            def get_c(i: int) -> str:
                return row[i].strip() if len(row) > i and row[i] else ""

            discord_id, roblox = get_c(0), get_c(2)
            if not discord_id and not roblox:
                continue
            index_list.append({
                "row": idx,
                "discord_id": discord_id,
                "discord_tag": get_c(1).lstrip("@"),
                "roblox": roblox,
                "nom_usage": get_c(3) or roblox,
                "grade": get_c(6) or "EVAT",
                "has_diplome": get_c(col_index - 1).upper() == "TRUE",
            })
        return index_list

    def _apply_diplome_batch(self, rows: list[int], col_index: int, valeur: bool):
        ws = get_recensement_worksheet(self.gc, self.spreadsheet_id)
        updates = [{"range": cellule(col_index, r), "values": [[valeur]]} for r in rows]
        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")

    async def _diplome_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        cur = current.strip().lower()
        choix = []
        for code, cfg in tous_les_diplomes(inclure_hors_commande=False).items():
            if cur in code.lower():
                choix.append(app_commands.Choice(name=f"{code} — {TYPE_LABELS[cfg['type']]}", value=code))
        return choix[:25]

    @app_commands.command(
        name="brevet",
        description="Attribue une spécialisation ou un brevet (capture d'écran et/ou liste de membres)."
    )
    @app_commands.guild_only()
    @app_commands.describe(
        diplome="La spécialisation ou le brevet concerné",
        image="Capture d'écran de la liste des joueurs présents (optionnel)",
        membres="Mentions, pseudos Roblox ou noms d'usage, séparés par une virgule ou un espace (optionnel)",
        notes="Observations sur la formation (optionnel)",
        retirer="Retirer le diplôme au lieu de l'attribuer (administrateurs uniquement)",
    )
    @app_commands.autocomplete(diplome=_diplome_autocomplete)
    async def brevet(
        self,
        interaction: discord.Interaction,
        diplome: str,
        image: Optional[discord.Attachment] = None,
        membres: str = "",
        notes: str = "",
        retirer: bool = False,
    ):
        autorise = is_user_admin(interaction.user) if retirer else is_formateur_or_admin(interaction.user)
        if not autorise:
            await interaction.response.send_message(embed=get_admin_error_embed(), ephemeral=True)
            return

        cfg = get_diplome(diplome)
        if cfg is None or cfg["code"] not in tous_les_diplomes(inclure_hors_commande=False):
            await interaction.response.send_message(
                f"⚠️ `{diplome}` n'est pas un diplôme géré par cette commande (le FGI passe par `/fgi`).",
                ephemeral=True
            )
            return
        if image is None and not membres.strip():
            await interaction.response.send_message(
                "⚠️ Donne au moins une capture d'écran (`image`) ou une liste de `membres`.", ephemeral=True
            )
            return
        if image is not None and (not image.content_type or not image.content_type.startswith("image/")):
            await interaction.response.send_message("⚠️ Le fichier joint doit être une image valide (PNG, JPG...).", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            detected: list[str] = []
            if image is not None:
                # On réutilise le moteur OCR déjà chargé par le Cog Operations (un seul modèle en mémoire)
                ops = self.bot.get_cog("Operations")
                if ops is None:
                    await interaction.followup.send("❌ Le module d'OCR (Cog `Operations`) n'est pas chargé.")
                    return
                image_bytes = await image.read()
                detected, sheet_index = await asyncio.gather(
                    asyncio.to_thread(ops._extract_pseudos_from_image, image_bytes),
                    asyncio.to_thread(self._fetch_sheet_index, cfg["col_index"]),
                )
            else:
                sheet_index = await asyncio.to_thread(self._fetch_sheet_index, cfg["col_index"])

            view = DiplomeConfirmView(
                cog=self,
                author=interaction.user,
                diplome=cfg,
                retrait=retirer,
                sheet_index=sheet_index,
                detected_raw=detected,
                manual_raw=split_pseudos(membres),
                image_url=image.url if image else None,
                notes=notes.strip(),
            )
            view.message = await interaction.followup.send(embed=view.build_preview_embed(), view=view, wait=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Une erreur est survenue : `{e}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Diplomes(bot))