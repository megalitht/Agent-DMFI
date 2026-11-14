# utils.py
from __future__ import annotations
import re
import difflib
import functools
import discord
from discord.ext import commands
import gspread

from data import ADMIN_MASTER_ID, ROLE_FORMATEUR_IDS, WORKSHEET_NAMES


# =====================================================================
# PERMISSIONS
# =====================================================================

def is_user_admin(user: discord.Member | discord.User) -> bool:
    """Vérifie si l'utilisateur est administrateur du serveur ou possède l'ID maître."""
    if user.id == ADMIN_MASTER_ID:
        return True
    if isinstance(user, discord.Member):
        return user.guild_permissions.administrator
    return False


def is_user_formateur(user: discord.Member | discord.User) -> bool:
    """Vérifie si l'utilisateur possède un des rôles Formateur."""
    if isinstance(user, discord.Member):
        return any(r.id in ROLE_FORMATEUR_IDS for r in user.roles)
    return False


def is_formateur_or_admin(user: discord.Member | discord.User) -> bool:
    return is_user_admin(user) or is_user_formateur(user)


def get_admin_error_embed() -> discord.Embed:
    """Génère l'embed d'erreur de permission avec le GIF."""
    embed_error = discord.Embed(
        description="Hop hop hop ! Tu n'as pas les perms !",
        color=discord.Color.red()
    )
    embed_error.set_image(
        url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif"
    )
    return embed_error


def _permission_decorator(check):
    """Fabrique un décorateur compatible avec discord.Interaction et commands.Context."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Si c'est dans un Cog, args[0] est 'self' et args[1] est Context ou Interaction
            target = args[0]
            if not isinstance(target, (discord.Interaction, commands.Context)) and len(args) > 1:
                target = args[1]

            user = target.user if isinstance(target, discord.Interaction) else target.author

            if not check(user):
                embed_error = get_admin_error_embed()
                if isinstance(target, discord.Interaction):
                    await target.response.send_message(embed=embed_error, ephemeral=True)
                else:
                    await target.send(embed=embed_error, ephemeral=True)
                return

            return await func(*args, **kwargs)
        return wrapper
    return decorator


# --- DÉCORATEURS ---
admin_only = _permission_decorator(is_user_admin)
formateur_only = _permission_decorator(is_formateur_or_admin)  # Formateurs + Admins


# =====================================================================
# GOOGLE SHEETS
# =====================================================================

# Numéro de "version" du recensement : augmente à chaque suppression de ligne.
# Une suppression fait remonter les lignes suivantes, donc une fenêtre de confirmation
# ouverte avant (/fgi, /operation, /brevet...) ne doit plus écrire avec ses anciens numéros.
_version_recensement = 0


def version_recensement() -> int:
    return _version_recensement


def signaler_suppression_lignes():
    global _version_recensement
    _version_recensement += 1


MESSAGE_LIGNES_DECALEES = (
    "⚠️ Des lignes du recensement ont été supprimées depuis l'ouverture de cette fenêtre "
    "(un joueur a quitté le serveur ou a été retiré). Pour ne pas écrire sur la mauvaise ligne, "
    "rien n'a été modifié : relance la commande."
)

def get_recensement_worksheet(gc: gspread.Client, spreadsheet_id: str) -> gspread.Worksheet:
    """Ouvre l'onglet de recensement (avec ou sans espace final dans son nom)."""
    sh = gc.open_by_key(spreadsheet_id)
    for name in WORKSHEET_NAMES:
        try:
            return sh.worksheet(name)
        except gspread.WorksheetNotFound:
            continue
    return sh.get_worksheet(0)


# =====================================================================
# MEMBRES
# =====================================================================

def split_pseudos(texte: str) -> list[str]:
    """Découpe une saisie 'a, b c' ou des mentions en liste de pseudos."""
    return [t.strip() for t in re.split(r"[,;\s\n]+", texte or "") if t.strip()]


def find_player(sheet_index: list[dict], query: str, allow_discord: bool = True) -> dict | None:
    """
    Retrouve un membre dans l'index du Sheet à partir d'une mention, d'un ID Discord,
    d'un @Discord, d'un pseudo Roblox ou d'un nom d'usage (tolérant aux erreurs OCR).
    """
    q = re.sub(r"[<@!>]", "", query.strip()).lower()
    if len(q) < 2:
        return None

    for entry in sheet_index:
        if allow_discord and q in (entry["discord_id"].lower(), entry["discord_tag"].lower()):
            return entry
        if q in (entry["roblox"].lower(), entry["nom_usage"].lower()):
            return entry

    champs = [("roblox", 0.84), ("nom_usage", 0.84)]
    if allow_discord:
        champs.insert(0, ("discord_tag", 0.82))
    for champ, cutoff in champs:
        mapping = {e[champ].lower(): e for e in sheet_index if e[champ]}
        proche = difflib.get_close_matches(q, list(mapping.keys()), n=1, cutoff=cutoff)
        if proche:
            return mapping[proche[0]]
    return None


async def rename_with_grade(membre: discord.Member, new_grade: str, fallback_usage: str, reason: str | None = None) -> str:
    """Remplace uniquement l'encadré [GRADE] du surnom en conservant le reste."""
    current_nick = membre.display_name
    if re.match(r"^\[[^\]]+\]", current_nick):
        nouveau_pseudo = re.sub(r"^\[[^\]]+\]\s*", f"[{new_grade}] ", current_nick)
    else:
        nouveau_pseudo = f"[{new_grade}] {current_nick or fallback_usage}"

    nouveau_pseudo = nouveau_pseudo[:32]
    if nouveau_pseudo == membre.nick:
        return f"✅ `{nouveau_pseudo}`"
    try:
        await membre.edit(nick=nouveau_pseudo, reason=reason or f"Promotion DMFI -> {new_grade}")
        return f"✅ `{nouveau_pseudo}`"
    except discord.Forbidden:
        return "⚠️ Renommage impossible (rôle supérieur au bot)"
    except discord.HTTPException as e:
        return f"⚠️ Erreur renommage ({e.status})"
