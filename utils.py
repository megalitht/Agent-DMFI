# utils.py
import json
import os
import functools
import discord

DATA_FILE = "event_data.json"

# --- GESTION DONNÉES EVENT ---
def load_event_data():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return None

def save_event_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- DÉCORATEUR ADMIN ---
def admin_only(func):
    """
    Décorateur custom pour vérifier les permissions admin.
    """
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        # Dans un Cog, le premier argument est 'self', le second est 'interaction'.
        # Si la fonction est hors classe, le premier est 'interaction'.
        # On gère le cas où 'interaction' serait le 2ème argument (cas d'une méthode de classe)
        real_interaction = interaction
        if not isinstance(interaction, discord.Interaction):
            # C'est probablement 'self', donc l'interaction est dans args[0]
            real_interaction = args[0]

        if not real_interaction.user.guild_permissions.administrator:
            embed_error = discord.Embed(description="Hop hop hop ! Tu n'as pas les perms !", color=discord.Color.red())
            embed_error.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif")
            await real_interaction.response.send_message(embed=embed_error, ephemeral=True)
            return 
        
        return await func(interaction, *args, **kwargs)
    return wrapper