# utils.py
from __future__ import annotations
import functools
import discord
from discord.ext import commands

ADMIN_MASTER_ID = 602585381120114698

def is_user_admin(user: discord.Member | discord.User) -> bool:
    """Vérifie si l'utilisateur est administrateur du serveur ou possède l'ID maître."""
    if user.id == ADMIN_MASTER_ID:
        return True
    if isinstance(user, discord.Member):
        return user.guild_permissions.administrator
    return False

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

# --- DÉCORATEUR ADMIN ---
def admin_only(func):
    """
    Décorateur custom compatible avec discord.Interaction et commands.Context.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Si c'est dans un Cog, args[0] est 'self' et args[1] est Context ou Interaction
        target = args[0]
        if not isinstance(target, (discord.Interaction, commands.Context)) and len(args) > 1:
            target = args[1]

        user = target.user if isinstance(target, discord.Interaction) else target.author

        if not is_user_admin(user):
            embed_error = get_admin_error_embed()
            if isinstance(target, discord.Interaction):
                await target.response.send_message(embed=embed_error, ephemeral=True)
            else:
                await target.send(embed=embed_error, ephemeral=True)
            return

        return await func(*args, **kwargs)
    return wrapper