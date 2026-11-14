from __future__ import annotations
import io
import os
import re
import asyncio
import difflib
from datetime import datetime, time
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
from discord.ext import commands, tasks
import gspread
import numpy as np
from PIL import Image, ImageOps, ImageEnhance
import easyocr
from utils import (
    admin_only, formateur_only, is_user_admin, is_formateur_or_admin,
    get_admin_error_embed, get_recensement_worksheet, rename_with_grade,
    version_recensement, MESSAGE_LIGNES_DECALEES,
)
from data import (
    GRADES_PROGRESSION, GRADES_META, GRADE_ROLES,
    FGI_ROLE_REMOVE_ID, FGI_ROLES_ADD_IDS, BREVET_ROLES,
    COL_GRADE, COL_POINTS, SPREADSHEET_ID_DEFAUT, cellule,
)

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="torch.ao.nn.quantized")

def format_fr_float(val: float) -> str:
    """Formate un float au format français (ex: 1.5 -> '1,5', 2.0 -> '2')."""
    if val.is_integer():
        return str(int(val))
    return f"{val:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def parse_fr_float(val_str: str) -> float:
    """Convertit une chaîne avec virgule ou point en float."""
    if not val_str:
        return 0.0
    try:
        return float(str(val_str).strip().replace(",", "."))
    except ValueError:
        return 0.0

def add_one_third(pts: float) -> float:
    """Ajoute exactement 1/3 de point en base 6 (0 -> 0,33 -> 0,67 -> 1)."""
    sixths = round(pts * 6) + 2
    return round(sixths / 6, 2)

# --- CONFIGURATION DES PROMOTIONS AUTOMATIQUES (12h00 et 19h00 heure de Paris) ---
PARIS_TZ = ZoneInfo("Europe/Paris")
PROMO_TIMES = [
    time(hour=12, minute=0, tzinfo=PARIS_TZ),
    time(hour=19, minute=0, tzinfo=PARIS_TZ),
]

# Les tables (grades, rôles, FGI...) sont dans data.py

# --- 1. POP-UP POUR AJOUTER / RETIRER DES PSEUDOS AVANT VALIDATION ---
class ModifierListeModal(discord.ui.Modal, title="Modifier la liste des participants"):
    ajouter = discord.ui.TextInput(
        label="Ajouter des pseudos (Roblox ou Nom d'usage)",
        placeholder="Sépare par une virgule ou un espace (ex: Toane44, Karma0x7)",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    retirer = discord.ui.TextInput(
        label="Retirer des pseudos de la liste",
        placeholder="Sépare par une virgule ou un espace (ex: Mmx132k)",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, view: "OperationConfirmView"):
        super().__init__()
        self.op_view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Traitement des ajouts
        if self.ajouter.value.strip():
            tokens_add = [t.strip() for t in re.split(r"[,;\s\n]+", self.ajouter.value) if t.strip()]
            for token in tokens_add:
                self.op_view.add_manual_pseudo(token)

        # Traitement des retraits
        if self.retirer.value.strip():
            tokens_rem = [t.strip() for t in re.split(r"[,;\s\n]+", self.retirer.value) if t.strip()]
            for token in tokens_rem:
                self.op_view.remove_pseudo(token)

        nouvel_embed = self.op_view.build_preview_embed()
        await self.op_view.message.edit(embed=nouvel_embed, view=self.op_view)
        await interaction.followup.send("✅ Liste des participants mise à jour.", ephemeral=True)


# --- 2. VUE DE CONFIRMATION DE L'OPÉRATION ---
class OperationConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "Operations",
        author: discord.Member,
        points_to_add: float,
        type_event: str,
        image_url: str,
        sheet_index: list[dict],
        detected_raw: list[str]
    ):
        super().__init__(timeout=900)  # Expire après 15 minutes
        self.version_sheet = version_recensement()  # Voir utils.signaler_suppression_lignes
        self.cog = cog
        self.author = author
        self.points_to_add = points_to_add
        self.type_event = type_event
        self.image_url = image_url
        self.sheet_index = sheet_index
        self.message: discord.Message | None = None

        # Dictionnaires des joueurs résolus (clé = numéro de ligne dans le Sheet)
        self.eligible_players: dict[int, dict] = {}
        self.special_grade_players: dict[int, dict] = {}
        self.unmatched_names: list[str] = []

        for raw_name in detected_raw:
            self._match_and_classify(raw_name)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_user_admin(interaction.user):
            await interaction.response.send_message(embed=get_admin_error_embed(), ephemeral=True)
            return False
        return True

    def _find_in_sheet(self, query: str) -> dict | None:
        q_low = query.strip().lower()
        if len(q_low) < 2:
            return None

        # 1. Correspondance exacte sur le pseudo Roblox ou le Nom d'usage
        for entry in self.sheet_index:
            if entry["roblox"].lower() == q_low or entry["nom_usage"].lower() == q_low:
                return entry

        # 2. Correspondance approchée (tolérance aux erreurs OCR type 0/O, 1/l)
        roblox_map = {e["roblox"].lower(): e for e in self.sheet_index if e["roblox"]}
        close = difflib.get_close_matches(q_low, list(roblox_map.keys()), n=1, cutoff=0.84)
        if close:
            return roblox_map[close[0]]

        usage_map = {e["nom_usage"].lower(): e for e in self.sheet_index if e["nom_usage"]}
        close_usage = difflib.get_close_matches(q_low, list(usage_map.keys()), n=1, cutoff=0.84)
        if close_usage:
            return usage_map[close_usage[0]]

        return None

    def _match_and_classify(self, name: str):
        entry = self._find_in_sheet(name)
        if not entry:
            if name not in self.unmatched_names:
                self.unmatched_names.append(name)
            return

        row_num = entry["row"]
        if entry["is_numeric_req"]:
            self.eligible_players[row_num] = entry
        else:
            self.special_grade_players[row_num] = entry

    def add_manual_pseudo(self, name: str):
        # Si le pseudo était dans les introuvables, on le retire avant de re-tester
        self.unmatched_names = [u for u in self.unmatched_names if u.lower() != name.lower()]
        self._match_and_classify(name)

    def remove_pseudo(self, name: str):
        q_low = name.strip().lower()
        self.unmatched_names = [u for u in self.unmatched_names if u.lower() != q_low]

        for row_num in list(self.eligible_players.keys()):
            p = self.eligible_players[row_num]
            if p["roblox"].lower() == q_low or p["nom_usage"].lower() == q_low:
                del self.eligible_players[row_num]

        for row_num in list(self.special_grade_players.keys()):
            p = self.special_grade_players[row_num]
            if p["roblox"].lower() == q_low or p["nom_usage"].lower() == q_low:
                del self.special_grade_players[row_num]

    def build_preview_embed(self, finalized: bool = False) -> discord.Embed:
        pts_fmt = format_fr_float(self.points_to_add)
        title = "✅ Rapport d'opération validé" if finalized else "📋 Aperçu de l'opération (En attente de confirmation)"
        color = discord.Color.green() if finalized else discord.Color.orange()

        embed = discord.Embed(
            title=title,
            description=(
                f"**Host / Responsable :** {self.author.mention}\n"
                f"**Type d'évent :** `{self.type_event}`\n"
                f"**Points accordés :** `+{pts_fmt} pt(s)`"
            ),
            color=color,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=self.image_url)

        # 1. Joueurs éligibles aux points
        if self.eligible_players:
            lignes_eligibles = []
            for p in self.eligible_players.values():
                old_pts = p["points_float"]
                new_pts = old_pts + self.points_to_add
                req_pts = p["requis_float"]
                promo_tag = " 🎉 **(100% atteint !)**" if req_pts > 0 and new_pts >= req_pts else ""
                lignes_eligibles.append(
                    f"• **{p['nom_usage']}** (`{p['roblox']}` — {p['grade']}) : "
                    f"`{format_fr_float(old_pts)}` ➔ **`{format_fr_float(new_pts)} / {format_fr_float(req_pts)}`**{promo_tag}"
                )
            texte_eligibles = "\n".join(lignes_eligibles)
            if len(texte_eligibles) > 1020:
                texte_eligibles = texte_eligibles[:1015] + "\n..."
        else:
            texte_eligibles = "*Aucun joueur éligible aux points détecté.*"

        embed.add_field(
            name=f"✅ Joueurs crédités ({len(self.eligible_players)})",
            value=texte_eligibles,
            inline=False
        )

        # 2. Joueurs présents mais avec un grade à condition (EVAT, CC1, SGT, ADJ, Officiers...)
        if self.special_grade_players:
            lignes_spec = [
                f"• **{p['nom_usage']}** (`{p['roblox']}` — {p['grade']}) : *Requis : {p['requis_raw']}*"
                for p in self.special_grade_players.values()
            ]
            texte_spec = "\n".join(lignes_spec)
            if len(texte_spec) > 1020:
                texte_spec = texte_spec[:1015] + "\n..."
            embed.add_field(
                name=f"ℹ️ Présents hors système de points ({len(self.special_grade_players)})",
                value=texte_spec,
                inline=False
            )

        # 3. Pseudos non reconnus par l'OCR
        if self.unmatched_names:
            embed.add_field(
                name=f"⚠️ Pseudos non trouvés sur le Sheet ({len(self.unmatched_names)})",
                value=", ".join(f"`{u}`" for u in self.unmatched_names)[:1020],
                inline=False
            )

        
        
        if not finalized:
            embed.set_footer(text="Vérifie la liste puis clique sur Confirmer ou Modifier.")
        else:
            embed.set_footer(text="Google Sheet mis à jour avec succès.")

        return embed
    
    @discord.ui.button(label="Confirmer l'ajout", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.eligible_players:
            await interaction.response.send_message(
                "⚠️ Aucun joueur éligible aux points dans la liste actuelle.",
                ephemeral=True
            )
            return

        if version_recensement() != self.version_sheet:
            await interaction.response.send_message(MESSAGE_LIGNES_DECALEES, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await asyncio.to_thread(
                self.cog._apply_points_batch,
                self.eligible_players,
                self.points_to_add
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la mise à jour Google Sheet : `{e}`", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True

        embed_final = self.build_preview_embed(finalized=True)
        await interaction.message.edit(embed=embed_final, view=None)
        await interaction.followup.send(
            f"✅ Points (`+{format_fr_float(self.points_to_add)}`) ajoutés à **{len(self.eligible_players)}** membre(s) !",
            ephemeral=True
        )

    @discord.ui.button(label="Ajouter / Retirer un pseudo", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModifierListeModal(self))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        embed.title = "❌ Opération annulée"
        embed.color = discord.Color.red()
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("🛑 L'opération a été annulée.", ephemeral=True)

# --- 2bis. POP-UP & VUE DE CONFIRMATION POUR LA FGI ---
class ModifierFGIModal(discord.ui.Modal, title="Modifier la liste de la FGI"):
    ajouter_evat = discord.ui.TextInput(
        label="Ajouter des EVAT (Roblox ou Nom d'usage)",
        placeholder="Sépare par une virgule ou un espace",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    ajouter_inst = discord.ui.TextInput(
        label="Ajouter des Instructeurs (Pseudo Discord/Nom)",
        placeholder="Sépare par une virgule ou un espace",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    retirer = discord.ui.TextInput(
        label="Retirer (EVAT ou Instructeur)",
        placeholder="Sépare par une virgule ou un espace",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    notes = discord.ui.TextInput(
        label="Notes / Observations",
        placeholder="Observations sur la session...",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, view: "FGIConfirmView"):
        super().__init__()
        self.fgi_view = view
        self.notes.default = view.notes  # Pré-remplit avec la note actuelle

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if self.ajouter_evat.value.strip():
            tokens = [t.strip() for t in re.split(r"[,;\s\n]+", self.ajouter_evat.value) if t.strip()]
            for token in tokens:
                self.fgi_view.add_manual_evat(token)

        if self.ajouter_inst.value.strip():
            tokens = [t.strip() for t in re.split(r"[,;\s\n]+", self.ajouter_inst.value) if t.strip()]
            for token in tokens:
                self.fgi_view.add_instructor(token)

        if self.retirer.value.strip():
            tokens = [t.strip() for t in re.split(r"[,;\s\n]+", self.retirer.value) if t.strip()]
            for token in tokens:
                self.fgi_view.remove_entry(token)

        # Met à jour la note avec la valeur du modal
        self.fgi_view.notes = self.notes.value.strip()

        nouvel_embed = self.fgi_view.build_preview_embed()
        await self.fgi_view.message.edit(embed=nouvel_embed, view=self.fgi_view)
        await interaction.followup.send("✅ Liste de la FGI mise à jour.", ephemeral=True)


class FGIConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "Operations",
        author: discord.Member,
        image_url: str,
        sheet_index: list[dict],
        detected_raw: list[str],
        raw_instructors: list[str],
        notes: str = ""
    ):
        super().__init__(timeout=900)
        self.version_sheet = version_recensement()  # Voir utils.signaler_suppression_lignes
        self.cog = cog
        self.author = author
        self.image_url = image_url
        self.sheet_index = sheet_index
        self.notes = notes
        self.message: discord.Message | None = None

        self.evat_players: dict[int, dict] = {}
        self.other_grade_players: dict[int, dict] = {}
        self.instructors: dict[int, dict] = {}
        self.unmatched_names: list[str] = []
        self.unmatched_instructors: list[str] = []

        for raw_inst in raw_instructors:
            self.add_instructor(raw_inst)

        for raw_name in detected_raw:
            self._match_and_classify_evat(raw_name)

    # Formateurs + Admins
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_formateur_or_admin(interaction.user):
            await interaction.response.send_message(embed=get_admin_error_embed(), ephemeral=True)
            return False
        return True

    def _find_player(self, query: str, allow_discord: bool = False) -> dict | None:
        q_clean = re.sub(r"[<@!>]", "", query.strip()).lower()
        if len(q_clean) < 2:
            return None

        # 1. Correspondance exacte (ID Discord, @Discord, Roblox ou Nom d'usage)
        for entry in self.sheet_index:
            if allow_discord and (entry["discord_id"].lower() == q_clean or entry["discord_tag"].lower() == q_clean):
                return entry
            if entry["roblox"].lower() == q_clean or entry["nom_usage"].lower() == q_clean:
                return entry

        # 2. Correspondance approchée (tolérance OCR / frappe)
        if allow_discord:
            discord_map = {e["discord_tag"].lower(): e for e in self.sheet_index if e["discord_tag"]}
            close_disc = difflib.get_close_matches(q_clean, list(discord_map.keys()), n=1, cutoff=0.82)
            if close_disc:
                return discord_map[close_disc[0]]

        roblox_map = {e["roblox"].lower(): e for e in self.sheet_index if e["roblox"]}
        close_rob = difflib.get_close_matches(q_clean, list(roblox_map.keys()), n=1, cutoff=0.84)
        if close_rob:
            return roblox_map[close_rob[0]]

        usage_map = {e["nom_usage"].lower(): e for e in self.sheet_index if e["nom_usage"]}
        close_use = difflib.get_close_matches(q_clean, list(usage_map.keys()), n=1, cutoff=0.84)
        if close_use:
            return usage_map[close_use[0]]

        return None

    def _match_and_classify_evat(self, name: str):
        entry = self._find_player(name, allow_discord=False)
        if not entry:
            if name not in self.unmatched_names:
                self.unmatched_names.append(name)
            return

        row_num = entry["row"]
        # Si le joueur est déjà listé comme instructeur de la session, on ne le duplique pas
        if row_num in self.instructors:
            return

        if entry["grade"] == "EVAT":
            self.evat_players[row_num] = entry
        else:
            self.other_grade_players[row_num] = entry

    def add_manual_evat(self, name: str):
        self.unmatched_names = [u for u in self.unmatched_names if u.lower() != name.lower()]
        self._match_and_classify_evat(name)

    def add_instructor(self, name: str):
        self.unmatched_instructors = [u for u in self.unmatched_instructors if u.lower() != name.lower()]
        entry = self._find_player(name, allow_discord=True)
        if not entry:
            if name not in self.unmatched_instructors:
                self.unmatched_instructors.append(name)
            return

        row_num = entry["row"]
        self.other_grade_players.pop(row_num, None)
        self.evat_players.pop(row_num, None)
        self.instructors[row_num] = entry

    def remove_entry(self, name: str):
        q_low = re.sub(r"[<@!>]", "", name.strip()).lower()
        self.unmatched_names = [u for u in self.unmatched_names if u.lower() != q_low]
        self.unmatched_instructors = [u for u in self.unmatched_instructors if u.lower() != q_low]

        for d in (self.evat_players, self.other_grade_players, self.instructors):
            for row_num in list(d.keys()):
                p = d[row_num]
                if q_low in {p["roblox"].lower(), p["nom_usage"].lower(), p["discord_tag"].lower(), p["discord_id"].lower()}:
                    del d[row_num]

    def build_preview_embed(self, finalized: bool = False) -> discord.Embed:
        title = "✅ Rapport de FGI validé" if finalized else "🪖 Aperçu de la FGI (En attente de confirmation)"
        color = discord.Color.green() if finalized else discord.Color.orange()

        embed = discord.Embed(
            title=title,
            description=(
                f"**Responsable :** {self.author.mention}\n"
                f"**Promotion Recrues :** `EVAT` ➔ **`SDT`** *(Promotion & renommage directs)*\n"
                f"**Bonus Instructeurs :** `+1/3 pt` *(Ajouté au Sheet pour le cycle de 12h/19h)*"
            ),
            color=color,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=self.image_url)

        # 1. Instructeurs (+1/3 pt)
        if self.instructors:
            lignes_inst = []
            for p in self.instructors.values():
                disc_mention = f"<@{p['discord_id']}>" if p["discord_id"].isdigit() else f"`@{p['discord_tag']}`"
                if p["is_numeric_req"]:
                    old_pts = p["points_float"]
                    new_pts = add_one_third(old_pts)
                    req_pts = p["requis_float"]
                    promo_tag = " 🎉 **(100% ➔ Cycle 12h/19h)**" if req_pts > 0 and new_pts >= req_pts else ""
                    lignes_inst.append(
                        f"• **{p['nom_usage']}** ({disc_mention} — {p['grade']}) : "
                        f"`{format_fr_float(old_pts)}` ➔ **`{format_fr_float(new_pts)} / {format_fr_float(req_pts)}`**{promo_tag}"
                    )
                else:
                    lignes_inst.append(
                        f"• **{p['nom_usage']}** ({disc_mention} — {p['grade']}) : *Hors système de points ({p['requis_raw']})*"
                    )
            embed.add_field(
                name=f"🎖️ Instructeurs (+1/3 pt) ({len(self.instructors)})",
                value="\n".join(lignes_inst)[:1020],
                inline=False
            )
        else:
            embed.add_field(
                name="🎖️ Instructeurs (+1/3 pt) (0)",
                value="*Aucun instructeur renseigné.*",
                inline=False
            )

        # 2. EVAT promus SDT
        if self.evat_players:
            lignes_evat = [
                f"• **{p['nom_usage']}** (`{p['roblox']}`) : `EVAT` ➔ **`SDT`**"
                for p in self.evat_players.values()
            ]
            texte_evat = "\n".join(lignes_evat)
            if len(texte_evat) > 1020:
                texte_evat = texte_evat[:1015] + "\n..."
        else:
            texte_evat = "*Aucun joueur au grade EVAT détecté.*"

        embed.add_field(
            name=f"✅ Recrues EVAT promues SDT ({len(self.evat_players)})",
            value=texte_evat,
            inline=False
        )

        # 3. Autres grades présents sur l'image (ignorés)
        if self.other_grade_players:
            lignes_autres = [
                f"• **{p['nom_usage']}** (`{p['roblox']}` — {p['grade']})"
                for p in self.other_grade_players.values()
            ]
            embed.add_field(
                name=f"ℹ️ Non-EVAT ignorés ({len(self.other_grade_players)})",
                value="\n".join(lignes_autres)[:1020],
                inline=False
            )

        # 4. Introuvables
        introuvables = self.unmatched_names + [f"[Inst] {u}" for u in self.unmatched_instructors]
        if introuvables:
            embed.add_field(
                name=f"⚠️ Pseudos non trouvés sur le Sheet ({len(introuvables)})",
                value=", ".join(f"`{u}`" for u in introuvables)[:1020],
                inline=False
            )

        embed.set_footer(
            text="Google Sheet et pseudos [SDT] mis à jour avec succès."
            if finalized else "Vérifie la liste puis clique sur Confirmer ou Modifier."
        )
        
        # 5. Notes / Observations de la FGI
        if self.notes:
            embed.add_field(
                name="📝 Notes / Observations",
                value=f"> {self.notes}",
                inline=False
            )

        return embed

    @discord.ui.button(label="Confirmer la FGI", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.evat_players and not self.instructors:
            await interaction.response.send_message(
                "⚠️ Aucun EVAT ni instructeur valide dans la liste actuelle.",
                ephemeral=True
            )
            return

        if version_recensement() != self.version_sheet:
            await interaction.response.send_message(MESSAGE_LIGNES_DECALEES, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await asyncio.to_thread(
                self.cog._apply_fgi_batch,
                self.evat_players,
                self.instructors
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la mise à jour Google Sheet : `{e}`", ephemeral=True)
            return

        # Renommage direct et mise à jour des rôles sur Discord pour tous les EVAT promus SDT
        guild = interaction.guild
        nb_renommes = 0
        nb_roles_maj = 0
        if guild:
            for p in self.evat_players.values():
                if p["discord_id"].isdigit():
                    uid = int(p["discord_id"])
                    membre = guild.get_member(uid)
                    if membre is None:
                        try:
                            membre = await guild.fetch_member(uid)
                        except discord.HTTPException:
                            membre = None
                    if membre:
                        statut_nick = await self.cog._rename_promoted_member(membre, "SDT", p["nom_usage"])
                        if statut_nick.startswith("✅"):
                            nb_renommes += 1

                        statut_roles = await self.cog._apply_fgi_roles(membre)
                        if statut_roles.startswith("✅"):
                            nb_roles_maj += 1

        for child in self.children:
            child.disabled = True

        embed_final = self.build_preview_embed(finalized=True)
        await interaction.message.edit(embed=embed_final, view=None)

        nb_inst_pts = sum(1 for i in self.instructors.values() if i["is_numeric_req"])
        await interaction.followup.send(
            f"✅ **FGI validée !**\n"
            f"• **{len(self.evat_players)}** `EVAT` promu(s) directement **`SDT`** "
            f"(`{nb_renommes}` renommé(s), `{nb_roles_maj}` avec rôles mis à jour).\n"
            f"• **{nb_inst_pts}** instructeur(s) crédité(s) de **`+1/3 pt`** sur le Sheet (pris en compte au prochain cycle de 12h/19h).",
            ephemeral=True
        )

    @discord.ui.button(label="Ajouter / Retirer", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModifierFGIModal(self))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        embed.title = "❌ FGI annulée"
        embed.color = discord.Color.red()
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("🛑 La FGI a été annulée.", ephemeral=True)
        
# --- 3. COG PRINCIPAL DES OPÉRATIONS ---
class Operations(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID") or SPREADSHEET_ID_DEFAUT
        self.credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")
        self.promo_channel_id = int(os.getenv("PROMO_CHANNEL_ID", "1508559680912363660"))
        self.gc = gspread.service_account(filename=self.credentials_path)
        # Initialisation unique du moteur OCR local (français/anglais)
        self.ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    async def cog_load(self):
        """Démarre la vérification automatique des promotions à 12h00 et 19h00."""
        if not self.auto_promotions_loop.is_running():
            self.auto_promotions_loop.start()

    async def cog_unload(self):
        """Arrête proprement la boucle si le Cog est déchargé."""
        if self.auto_promotions_loop.is_running():
            self.auto_promotions_loop.cancel()

    def _get_recensement_sheet(self):
        return get_recensement_worksheet(self.gc, self.spreadsheet_id)

    def _extract_pseudos_from_image(self, image_bytes: bytes) -> list[str]:
        """Prétraitement de la capture d'écran Roblox et extraction OCR 100% locale."""
        img = Image.open(io.BytesIO(image_bytes)).convert("L")

        # Agrandissement x2 et augmentation du contraste pour faciliter la lecture de la police Roblox
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(2.0)

        img_np = np.array(img)
        raw_texts = self.ocr_reader.readtext(img_np, detail=0)

        pseudos = []
        for line in raw_texts:
            # Nettoyage des caractères parasites éventuels autour du pseudo
            tokens = re.findall(r"[A-Za-z0-9_]{3,25}", line)
            for token in tokens:
                if token not in pseudos:
                    pseudos.append(token)
        return pseudos

    def _fetch_sheet_index(self) -> list[dict]:
        """Charge l'index des membres depuis le Google Sheet (colonnes A à J)."""
        ws = self._get_recensement_sheet()
        rows = ws.get("A2:J2000")

        index_list = []
        for idx, row in enumerate(rows, start=2):
            def get_c(i: int) -> str:
                return row[i].strip() if len(row) > i and row[i] else ""

            discord_id = get_c(0)
            discord_tag = get_c(1).lstrip("@")
            roblox = get_c(2)
            nom_usage = get_c(3)
            if not discord_id and not roblox:
                continue

            grade = get_c(6) or "EVAT"
            pts_raw = get_c(8)
            req_raw = get_c(9)

            try:
                req_float = float(req_raw.replace(",", "."))
                is_numeric_req = True
            except ValueError:
                req_float = 0.0
                is_numeric_req = False

            index_list.append({
                "row": idx,
                "discord_id": discord_id,
                "discord_tag": discord_tag,
                "roblox": roblox,
                "nom_usage": nom_usage or roblox,
                "grade": grade,
                "points_raw": pts_raw,
                "points_float": parse_fr_float(pts_raw),
                "requis_raw": req_raw or "Condition spéciale",
                "requis_float": req_float,
                "is_numeric_req": is_numeric_req,
            })
        return index_list

    def _apply_points_batch(self, eligible_players: dict[int, dict], points_to_add: float):
        """Met à jour en une seule requête batch toutes les cellules de points (Colonne I)."""
        ws = self._get_recensement_sheet()
        updates = []

        for row_num, p in eligible_players.items():
            nouveau_total = p["points_float"] + points_to_add
            updates.append({
                "range": f"I{row_num}",
                "values": [[format_fr_float(nouveau_total)]],
            })

        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")

    @commands.hybrid_command(
        name="operation",
        description="Analyse une capture d'écran de mission et prépare l'ajout des points."
    )

    @app_commands.default_permissions(administrator=True)
    @admin_only
    @app_commands.describe(
        image="La capture d'écran de la liste des joueurs (Tab)",
        points="Le nombre de points à accorder (ex: 0.5 ou 1)",
        type_event="Le nom ou type de l'événement (ex: Opération, Event politique...)"
    )
    async def operation(
        self,
        ctx: commands.Context,
        image: discord.Attachment,
        points: float,
        type_event: str = "Opération"
    ):
        if not image.content_type or not image.content_type.startswith("image/"):
            await ctx.send("⚠️ Le fichier joint doit être une image valide (PNG, JPG...).", ephemeral=True)
            return

        await ctx.defer()

        try:
            image_bytes = await image.read()

            # Exécution parallèle de l'OCR local et de la lecture du Google Sheet
            detected_pseudos, sheet_index = await asyncio.gather(
                asyncio.to_thread(self._extract_pseudos_from_image, image_bytes),
                asyncio.to_thread(self._fetch_sheet_index)
            )

            view = OperationConfirmView(
                cog=self,
                author=ctx.author,
                points_to_add=points,
                type_event=type_event,
                image_url=image.url,
                sheet_index=sheet_index,
                detected_raw=detected_pseudos
            )

            embed = view.build_preview_embed(finalized=False)
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg

        except Exception as e:
            await ctx.send(f"❌ Une erreur est survenue lors du traitement de l'opération : `{e}`")

    def _apply_fgi_batch(self, evat_players: dict[int, dict], instructors: dict[int, dict]):
        """
        Met à jour en une seule requête batch :
        - Les EVAT : Grade (G) -> 'SDT', Points (I) -> '0' et Brevet FGI (R) -> True
        - Les Instructeurs à points : Points (I) -> Points + 1/3
        """
        ws = self._get_recensement_sheet()
        updates = []

        for row_num in evat_players:
            updates.append({"range": cellule(COL_GRADE, row_num), "values": [["SDT"]]})
            updates.append({"range": cellule(COL_POINTS, row_num), "values": [["0"]]})
            # Coche la case FGI (colonne définie dans data.BREVET_ROLES)
            updates.append({"range": cellule(BREVET_ROLES["FGI"]["col_index"], row_num), "values": [[True]]})

        for row_num, inst in instructors.items():
            if inst["is_numeric_req"]:
                nouveau_total = add_one_third(inst["points_float"])
                updates.append({
                    "range": f"I{row_num}",
                    "values": [[format_fr_float(nouveau_total)]],
                })

        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")

    @commands.hybrid_command(
        name="fgi",
        description="Validation FGI automatique via capture d'écran (EVAT -> SDT + 1/3 pt aux instructeurs)."
    )
    @formateur_only  # Formateurs + Admins (pas de default_permissions, sinon la commande est masquée aux formateurs)
    @app_commands.describe(
        image="La capture d'écran de la liste des joueurs présents à la FGI",
        instructeurs="Pseudo(s) Discord ou mention(s) des instructeurs séparés par une virgule ou un espace (ex: @User1, @User2)", 
        notes="Observations ou commentaire sur le déroulement de la FGI (optionnel)"
    )
    async def fgi(
        self,
        ctx: commands.Context,
        image: discord.Attachment,
        instructeurs: str = "",
        notes: str = ""
    ):
        if not image.content_type or not image.content_type.startswith("image/"):
            await ctx.send("⚠️ Le fichier joint doit être une image valide (PNG, JPG...).", ephemeral=True)
            return

        await ctx.defer()

        try:
            image_bytes = await image.read()

            detected_pseudos, sheet_index = await asyncio.gather(
                asyncio.to_thread(self._extract_pseudos_from_image, image_bytes),
                asyncio.to_thread(self._fetch_sheet_index)
            )

            raw_instructors = [
                t.strip() for t in re.split(r"[,;\s\n]+", instructeurs) if t.strip()
            ] if instructeurs else []

            view = FGIConfirmView(
                cog=self,
                author=ctx.author,
                image_url=image.url,
                sheet_index=sheet_index,
                detected_raw=detected_pseudos,
                raw_instructors=raw_instructors,
                notes=notes.strip()
            )

            embed = view.build_preview_embed(finalized=False)
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg

        except Exception as e:
            await ctx.send(f"❌ Une erreur est survenue lors du traitement de la FGI : `{e}`")
            
    def _get_emoji_str(self, guild: discord.Guild, emoji_name: str | None) -> str:
        """Récupère l'émoji personnalisé du serveur au format <:nom:id>."""
        if not emoji_name or not guild:
            return ""
        emoji = discord.utils.get(guild.emojis, name=emoji_name)
        if not emoji:
            # Secours insensible à la casse
            emoji = next((e for e in guild.emojis if e.name.lower() == emoji_name.lower()), None)
        return str(emoji) if emoji else f":{emoji_name}:"

    async def _rename_promoted_member(self, membre: discord.Member, new_grade: str, fallback_usage: str) -> str:
        """Remplace uniquement l'encadré [GRADE] tout en conservant les suffixes du joueur."""
        return await rename_with_grade(membre, new_grade, fallback_usage)

    async def _apply_fgi_roles(self, membre: discord.Member) -> str:
        """Retire le rôle pré-FGI et attribue les 4 rôles post-FGI (dont SDT)."""
        guild = membre.guild
        role_remove = guild.get_role(FGI_ROLE_REMOVE_ID)
        roles_add = [
            r for r_id in FGI_ROLES_ADD_IDS
            if (r := guild.get_role(r_id)) is not None and r not in membre.roles
        ]

        try:
            if role_remove and role_remove in membre.roles:
                await membre.remove_roles(role_remove, reason="Validation FGI DMFI")
            if roles_add:
                await membre.add_roles(*roles_add, reason="Validation FGI DMFI")
            return "✅ Rôles FGI attribués"
        except discord.Forbidden:
            return "⚠️ Rôles impossibles (hiérarchie bot)"
        except discord.HTTPException as e:
            return f"⚠️ Erreur rôles ({e.status})"

    async def _update_grade_role(self, membre: discord.Member, old_grade: str, new_grade: str) -> str:
        """Retire le rôle de l'ancien grade et ajoute celui du nouveau grade lors d'une promotion."""
        guild = membre.guild
        old_role_id = GRADE_ROLES.get(old_grade)
        new_role_id = GRADE_ROLES.get(new_grade)

        role_remove = guild.get_role(old_role_id) if old_role_id else None
        role_add = guild.get_role(new_role_id) if new_role_id else None

        try:
            # Si le membre passe de EVAT à SDT via /promotion ou cycle auto, on applique tout le pack FGI
            if old_grade == "EVAT" and new_grade == "SDT":
                return await self._apply_fgi_roles(membre)

            if role_remove and role_remove in membre.roles:
                await membre.remove_roles(role_remove, reason=f"Promotion DMFI : {old_grade} -> {new_grade}")

            if role_add and role_add not in membre.roles:
                await membre.add_roles(role_add, reason=f"Promotion DMFI : {old_grade} -> {new_grade}")
                return f"✅ Rôle `{role_add.name}` attribué"
            elif not role_add:
                return f"ℹ️ Aucun rôle configuré pour `{new_grade}`"
            return "✅ Rôle déjà attribué"
        except discord.Forbidden:
            return "⚠️ Rôle impossible (hiérarchie bot)"
        except discord.HTTPException as e:
            return f"⚠️ Erreur rôle ({e.status})"

    def _scan_and_apply_promotions_sheet(self, target_discord_id: str | None = None) -> tuple[list[dict], str | None]:
        """
        Scanne le Google Sheet, vérifie l'éligibilité (100% ou examen validé),
        calcule le reliquat de points et met à jour les grades en batch.
        """
        ws = self._get_recensement_sheet()
        rows = ws.get("A2:K2000")

        promoted_players = []
        batch_updates = []
        target_found = False

        for idx, row in enumerate(rows, start=2):
            def get_c(i: int) -> str:
                return row[i].strip() if len(row) > i and row[i] else ""

            discord_id = get_c(0)
            roblox = get_c(2)
            nom_usage = get_c(3) or roblox

            if not discord_id and not roblox:
                continue

            if target_discord_id and discord_id != str(target_discord_id):
                continue

            target_found = True
            grade_actuel = get_c(6) or "EVAT"
            
            if grade_actuel == "EVAT":
                if target_discord_id:
                    return [], f"⚠️ **{nom_usage}** est EVAT. Sa promotion en SDT se fait uniquement via la commande `/fgi`."
                continue

            if grade_actuel not in GRADES_PROGRESSION or grade_actuel == "GDB":
                if target_discord_id:
                    return [], f"⚠️ **{nom_usage}** a déjà atteint le grade sommital (**{grade_actuel}**)."
                continue

            next_grade, default_req = GRADES_PROGRESSION[grade_actuel]
            req_raw = get_c(9) or default_req
            pts_raw = get_c(8)

            # Détermine si le grade actuel fonctionne aux points numériques ou à condition (brevet/examen)
            try:
                req_float = float(req_raw.replace(",", "."))
                is_numeric = req_float > 0
            except ValueError:
                req_float = 0.0
                is_numeric = False

            if is_numeric:
                pts_float = parse_fr_float(pts_raw)
                if pts_float >= req_float:
                    surplus = max(0.0, pts_float - req_float)
                else:
                    if target_discord_id:
                        pct = int(round((pts_float / req_float) * 100))
                        return [], (
                            f"❌ **Promotion refusée (Anti Free Rank-Up) :** **{nom_usage}** (**{grade_actuel}**) "
                            f"n'a que `{format_fr_float(pts_float)} / {format_fr_float(req_float)} pt(s)` (**{pct}%**). "
                            f"Il doit atteindre **100%** pour passer **{next_grade}**."
                        )
                    continue
            else:
                # Grade à examen/condition : vérifie que la colonne I (Points) contient une validation (ex: 1, OK, Validé)
                val_clean = pts_raw.strip().lower()
                is_validated = (
                    val_clean in {"1", "ok", "validé", "valide", "oui", "true", "100%"}
                    or parse_fr_float(pts_raw) >= 1.0
                )
                if is_validated:
                    surplus = 0.0
                else:
                    if target_discord_id:
                        return [], (
                            f"❌ **Promotion refusée (Anti Free Rank-Up) :** **{nom_usage}** (**{grade_actuel}** ➔ **{next_grade}**) "
                            f"n'a pas encore validé la condition **`{req_raw}`** sur le Google Sheet "
                            f"*(mets `1` ou `OK` dans la colonne Points `I` une fois son examen/dossier validé)*."
                        )
                    continue

            # Calcul de la nouvelle valeur de la colonne Points (I) pour le nouveau grade
            _, next_req_default = GRADES_PROGRESSION.get(next_grade, ("", ""))
            try:
                float(next_req_default.replace(",", "."))
                next_is_numeric = True
            except ValueError:
                next_is_numeric = False

            if next_is_numeric:
                # Conserve l'excédent de points (ou initialise à 0 si sortie d'examen type FMI/Test)
                new_pts_cell = format_fr_float(surplus) if is_numeric else "0"
            else:
                # Vide la cellule si le prochain grade est un examen/dossier pour éviter une double promotion
                new_pts_cell = ""

            batch_updates.append({"range": f"G{idx}", "values": [[next_grade]]})
            batch_updates.append({"range": f"I{idx}", "values": [[new_pts_cell]]})

            promoted_players.append({
                "row": idx,
                "discord_id": discord_id,
                "nom_usage": nom_usage,
                "old_grade": grade_actuel,
                "new_grade": next_grade,
                "new_pts": new_pts_cell,
            })

            if target_discord_id:
                break

        if target_discord_id and not target_found:
            return [], "⚠️ Ce membre est introuvable dans le Google Sheet de recensement."

        if batch_updates:
            ws.batch_update(batch_updates, value_input_option="USER_ENTERED")

        return promoted_players, None

    async def _run_promotions(self, target_discord_id: str | None = None) -> tuple[list[dict], str | None]:
        """Exécute la mise à jour Sheet, le renommage Discord et poste l'annonce dans le salon dédié."""
        promoted, error_msg = await asyncio.to_thread(
            self._scan_and_apply_promotions_sheet,
            target_discord_id
        )

        if not promoted:
            return [], error_msg

        channel = self.bot.get_channel(self.promo_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self.promo_channel_id)
            except discord.HTTPException:
                channel = None

        guild = channel.guild if channel else (self.bot.guilds[0] if self.bot.guilds else None)
        arrow_emoji = self._get_emoji_str(guild, "DMFI_Fleche1") if guild else "➡️"

        lignes_annonce = []
        for p in promoted:
            membre = None
            if guild and p["discord_id"].isdigit():
                uid = int(p["discord_id"])
                membre = guild.get_member(uid)
                if membre is None:
                    try:
                        membre = await guild.fetch_member(uid)
                    except discord.HTTPException:
                        membre = None

            # 1. Renommage et mise à jour du rôle de grade avant l'envoi du message
            if membre:
                p["rename_status"] = await self._rename_promoted_member(membre, p["new_grade"], p["nom_usage"])
                p["role_status"] = await self._update_grade_role(membre, p["old_grade"], p["new_grade"])
                mention_str = membre.mention
            else:
                p["rename_status"] = "⚠️ Membre absent du serveur"
                p["role_status"] = "⚠️ Rôle non modifié"
                mention_str = f"<@{p['discord_id']}>" if p["discord_id"].isdigit() else f"**[{p['new_grade']}] {p['nom_usage']}**"
                
            # 2. Construction de la ligne avec les émojis de galons et la flèche verte
            old_label, old_emoji_name = GRADES_META.get(p["old_grade"], (p["old_grade"], None))
            new_label, new_emoji_name = GRADES_META.get(p["new_grade"], (p["new_grade"], None))

            old_emoji = self._get_emoji_str(guild, old_emoji_name)
            new_emoji = self._get_emoji_str(guild, new_emoji_name)

            part_old = f"**{old_label}** {old_emoji}".strip()
            part_new = f"{new_emoji} **{new_label}**".strip()

            lignes_annonce.append(f"{mention_str}  {part_old} {arrow_emoji} {part_new}")

        # 3. Envoi de l'annonce dans le salon des promotions
        if channel:
            corps = "\n\n".join(lignes_annonce)
            annonce_msg = (
                f"# Suite à vos haptitude et à la décision de la haute hiérarchie.\n\n"
                f"{corps}\n\n"
                f"*Vos grades seront mise à jour automatiquement*\n"
                f"*Pour quelquonque problème, merci de contacter le support via un ticket.*\n"
                f"***Cordialement, l'ensemble de l'Etat Major et le Département de l'Enseignement Militaire de la DMFI.***"
            )
            await channel.send(annonce_msg)

        return promoted, None

    @tasks.loop(time=PROMO_TIMES)
    async def auto_promotions_loop(self):
        """Vérification automatique tous les jours à 12h00 et 19h00 (heure de Paris)."""
        try:
            promoted, _ = await self._run_promotions(target_discord_id=None)
            if promoted:
                print(f"[PROMOTIONS AUTO] {len(promoted)} membre(s) promu(s) avec succès.")
        except Exception as e:
            print(f"[ERREUR PROMOTIONS AUTO] : {e}")

    @auto_promotions_loop.before_loop
    async def before_auto_promotions(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(
        name="promotion",
        description="Vérifie l'éligibilité (100% ou examen validé) et promeut un membre ou tout le recensement."
    )
    @app_commands.default_permissions(administrator=True)
    @admin_only
    @app_commands.describe(
        membre="Le membre à promouvoir (laisse vide pour lancer le scan global de 12h/19h)"
    )
    async def promotion(self, ctx: commands.Context, membre: discord.Member = None):
        await ctx.defer(ephemeral=True)

        target_id = str(membre.id) if membre else None
        try:
            promoted, error_msg = await self._run_promotions(target_discord_id=target_id)
        except Exception as e:
            await ctx.send(f"❌ Erreur lors du traitement des promotions : `{e}`", ephemeral=True)
            return

        if error_msg:
            await ctx.send(error_msg, ephemeral=True)
            return

        if not promoted:
            await ctx.send("ℹ️ Aucun membre n'a atteint les **100%** (ou validé d'examen) pour le moment.", ephemeral=True)
            return

        resume = "\n".join(
            f"• **{p['nom_usage']}** : `{p['old_grade']}` ➔ **`{p['new_grade']}`** "
            f"(Reliquat : `{p['new_pts'] or '0'} pt` | {p['rename_status']} | {p['role_status']})"
            for p in promoted
        )
        await ctx.send(
            f"✅ **{len(promoted)} promotion(s) appliquée(s) et annoncée(s) dans <#{self.promo_channel_id}> :**\n{resume}",
            ephemeral=True
        )
        
async def setup(bot: commands.Bot):
    await bot.add_cog(Operations(bot))
