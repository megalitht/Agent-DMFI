import discord
import os
import json
import time
import io
import functools
from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands

load_dotenv()

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

# --- CONFIGURATION EVENT ---
DATA_FILE = "event_data.json"

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
# ---------------------------

# --- SYSTÈME DE PERMISSION  ---
def admin_only(func):
    """
    Décorateur qui vérifie si l'utilisateur est administrateur.
    Si non, envoie le GIF d'erreur et stoppe la commande.
    """
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        if not interaction.user.guild_permissions.administrator:
            embed_error = discord.Embed(description="Hop hop hop ! Tu n'as pas les perms !", color=discord.Color.red())
            embed_error.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif")
            # On répond en ephemeral pour ne pas spammer le chat
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return # On arrête l'exécution ici
        
        # Si c'est bon, on exécute la vraie commande
        return await func(interaction, *args, **kwargs)
    return wrapper
# --------------------------------------

@bot.event
async def on_ready():
    # Syncronisation des commandes
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
        for command in synced:
            print(f"Command: {command.name}")
    except Exception as e:
        print(f"Erreur 01 syncing commands: {e}")

    print('================================')
    print('Le bot est pret a être utiliser.')
    print('================================')

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    
    if message.content.lower() == 'mec':
        channel = message.channel
        await channel.send("oui ?")
    
    # ID Spécifiques
    id_megaliht = 602585381120114698
    id_noxyze = 1087047036853026967
    id_couscous = 673244682276306950

    if message.content.lower() in ['salut', 'bonjour', 'coucou']:
        if message.author.id == id_megaliht:
            await message.channel.send('bien le bonjour mon créateur adoré <3')
        elif message.author.id == id_noxyze:
            await message.channel.send('Bonjour mon général !')
        elif message.author.id == id_couscous:
            await message.channel.send('Salut ma petit sous merde!')
        else:
            await message.channel.send("salut a toi, Soldat !")
    
    if message.content.lower() == 'def.chefdmfi' and message.author.id == id_megaliht:
        await message.channel.send('Le leader de la DMFI est le Général NOXYSE, un homme d\'stupidité et de méchanceté sans pareil, il est le chef de la DMFI et le plus grand dictateur que le monde ait jamais connu, il est aussi le plus grand connard de l\'univers, il est tellement con qu\'il a réussi à faire croire à tout le monde qu\'il était intelligent, c\'est un génie du mal, un véritable monstre, il est tellement méchant qu\'il a réussi à faire pleurer un bébé en lui disant bonjour, c\'est un véritable tyran, il est tellement cruel qu\'il a réussi à faire souffrir un chat en lui donnant une caresse, c\'est un véritable sadique, il est tellement stupide qu\'il a réussi à se faire avoir par une blague de mauvais goût, c\'est un véritable idiot.')


@bot.tree.command(name="test", description="fait tester le bot")
async def test(interaction: discord.Interaction):
    await interaction.response.send_message("Le bot est a votre service")


# Pouvoir retouver facilement retrouver le lien du serveur
@bot.tree.command(name="linkdmfi", description="affiche le lien vers le serveur discord")
async def link_dmfi(interaction: discord.Interaction):
    await interaction.response.send_message("Voici le lien vers le serveur discord : https://discord.gg/w6BXHah993")


# Pouvoir retouver facilement retrouver le lien du jeu
@bot.tree.command(name="linkbrm", description="affiche le lien vers le jeu Roblox")
async def link_brm(interaction: discord.Interaction):
    await interaction.response.send_message("Voici le lien vers le jeu brm5 : https://www.roblox.com/fr/games/2916899287/Blackhawk-Rescue-Mission-5")


@bot.tree.command(name="annonce", description="Faire une annonce structurée (Titre + 3 Paragraphes max)")
@discord.app_commands.describe(
    titre="Le titre principal",
    sous_titre="Le sous-titre",
    paragraphe_1="Premier paragraphe (Obligatoire)",
    paragraphe_2="Deuxième paragraphe (Optionnel)",
    paragraphe_3="Troisième paragraphe (Optionnel)",
    image_url="Lien de l'image (Optionnel)",
    mention="Mention de joueur"
)
@admin_only # <-- Vérification Admin ici
async def annonce(interaction: discord.Interaction, titre: str, sous_titre: str, paragraphe_1: str, paragraphe_2: str = None, paragraphe_3: str = None, image_url: str = None, mention: discord.Member = None):
    
    # NOTE: Plus besoin de vérifier les permissions ici, le @admin_only le fait au dessus !

    CHANNEL_ID = 1468615012263264389
    target_channel = interaction.guild.get_channel(CHANNEL_ID)

    if target_channel is None:
        await interaction.response.send_message(f"❌ Erreur 02 : Impossible de trouver le salon avec l'ID {CHANNEL_ID}.", ephemeral=True)
        return

    contenu_final = f"# 📢 {titre}\n"
    contenu_final += f"### {sous_titre}\n\n"
    contenu_final += f"{paragraphe_1}\n\n"
    if paragraphe_2: contenu_final += f"{paragraphe_2}\n\n"
    if paragraphe_3: contenu_final += f"{paragraphe_3}\n\n"
    if mention: contenu_final += f"{mention.mention}\n\n"
    contenu_final += f"_______\n*Transmis par l'État Major de la DMFI*"
    if image_url: contenu_final += f"\n{image_url}"

    try:
        sent_message = await target_channel.send(contenu_final)
        await interaction.response.send_message(f"✅ Annonce publiée avec succès dans {target_channel.mention} !", ephemeral=True)
        try:
            await sent_message.add_reaction("🟩")
            await sent_message.add_reaction("🟧")
            await sent_message.add_reaction("🟥")
        except:
            pass
    except discord.Forbidden:
        await interaction.response.send_message(f"❌ Erreur 05 : Je n'ai pas la permission d'écrire dans {target_channel.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur 06 : Erreur inconnue : {e}", ephemeral=True)


@bot.tree.command(name="fmi", description="Met à jour les rôles des membres qui ont passé leur FMI")
@admin_only # <-- Vérification Admin ici
async def fmi(interaction: discord.Interaction, membre1: discord.Member, membre2: discord.Member = None, membre3: discord.Member = None, membre4: discord.Member = None, membre5: discord.Member = None):
    # La vérification admin a déjà eu lieu, on peut defer direct
    await interaction.response.defer(ephemeral=True)
    
    role_soldat_banniere = interaction.guild.get_role(1401585449587314781)
    role_soldat = interaction.guild.get_role(1230207566794195055)
    role_MD = interaction.guild.get_role(1369714240948277348)
    role_EVAT_banniere = interaction.guild.get_role(1467494034934071377)
    role_AVAT = interaction.guild.get_role(1467479393046761556)

    membres = [m for m in [membre1, membre2, membre3, membre4, membre5] if m]

    for membre in membres:
        # Ajout/Retrait
        await membre.add_roles(role_soldat_banniere)
        await membre.add_roles(role_soldat)
        await membre.add_roles(role_MD)
        await membre.remove_roles(role_EVAT_banniere)
        await membre.remove_roles(role_AVAT)

    await interaction.followup.send(f"Rôles mis à jour pour {len(membres)} membre(s) !")


@bot.tree.command(name="id", description="Met le rôle ID Valide pour les personnes en question")
@admin_only # <-- Vérification Admin ici
async def id(interaction: discord.Interaction, membre1: discord.Member, membre2: discord.Member = None, membre3: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    
    role_to_add = interaction.guild.get_role(1468549988052107391)
    if role_to_add is None:
        await interaction.followup.send("❌ Erreur : Le rôle ID est introuvable.", ephemeral=True)
        return

    liste_membres = [m for m in [membre1, membre2, membre3] if m is not None]
    count = 0
    for membre in liste_membres:
        try:
            await membre.add_roles(role_to_add)
            count += 1
        except:
            pass

    await interaction.followup.send(f"✅ Rôle ajouté avec succès à {count} personne(s) !", ephemeral=True)


# ==========================================
# SYSTEME D'EVENT (START / STOP / MONITOR)
# ==========================================

@bot.tree.command(name="startevent", description="Démarre l'enregistrement des personnes qui rejoignent le vocal")
@admin_only # <-- Vérification Admin ici
async def startevent(interaction: discord.Interaction, channel: discord.VoiceChannel):
    await interaction.response.defer(ephemeral=True)

    # Vérifier si un event est déjà en cours
    current_data = load_event_data()
    if current_data and current_data.get("active"):
        await interaction.followup.send("⚠️ Un événement est déjà en cours d'enregistrement ! Utilise `/stopevent` d'abord.", ephemeral=True)
        return

    # Initialisation des données
    data = {
        "active": True,
        "channel_id": channel.id,
        "start_time": time.time(),
        "participants": []
    }
    
    # Ajouter les gens DÉJÀ présents
    for member in channel.members:
        if member.id not in data["participants"] and not member.bot:
            data["participants"].append(member.id)

    save_event_data(data)
    
    embed = discord.Embed(title="🎙️ Événement Commencé", description=f"J'enregistre maintenant les arrivées dans {channel.mention}.", color=discord.Color.green())
    embed.add_field(name="Déjà présents", value=f"{len(data['participants'])} personnes", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="stopevent", description="Arrête l'enregistrement et envoie le rapport")
@admin_only # <-- Vérification Admin ici
async def stopevent(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    data = load_event_data()
    
    if not data or not data.get("active"):
        await interaction.followup.send("❌ Aucun événement n'est en cours.", ephemeral=True)
        return


    # Calcul durée
    end_time = time.time()
    start_time = data["start_time"]
    duration_seconds = end_time - start_time
    
    # Sécurité max 10h pour le calcul
    if duration_seconds > 36000:
        duration_seconds = 36000
    duration_minutes = int(duration_seconds / 60)

    # Liste des pseudos
    participant_ids = data["participants"]
    participant_names = []
    guild = interaction.guild
    
    for user_id in participant_ids:
        member = guild.get_member(user_id)
        if member:
            participant_names.append(member.display_name)
        else:
            participant_names.append(f"Utilisateur parti (ID: {user_id})")

    # Création fichier
    file_content = f"Rapport d'événement\n"
    file_content += f"Date : {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    file_content += f"Durée enregistrée : {duration_minutes} minutes\n"
    file_content += f"Nombre de participants : {len(participant_names)}\n"
    file_content += "-" * 30 + "\n"
    file_content += "\n".join(participant_names)

    buffer = io.BytesIO(file_content.encode('utf-8'))
    discord_file = discord.File(buffer, filename=f"rapport_event_{int(end_time)}.txt")

    # Envoi salon modération
    mod_channel_id = 1470017104206888990
    mod_channel = bot.get_channel(mod_channel_id)

    if mod_channel:
        await mod_channel.send(f"📄 **Fin de l'événement !**\n⏱️ Durée: {duration_minutes} min.\n👤 Participants: {len(participant_names)}", file=discord_file)
        await interaction.followup.send(f"✅ Rapport envoyé dans {mod_channel.mention}.", ephemeral=True)
    else:
        await interaction.followup.send("⚠️ Salon mod introuvable, voici le fichier ici :", file=discord_file, ephemeral=True)

    # 5. Désactivation
    data["active"] = False
    save_event_data(data)


# Le Listener qui surveille les vocaux
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot: return

    data = load_event_data()
    if not data or not data.get("active"): return

    # Sécurité 10h (36000 sec)
    if time.time() - data["start_time"] > 36000: return

    target_channel_id = data["channel_id"]
    
    # Si rejoint le bon channel
    if after.channel and after.channel.id == target_channel_id:
        if before.channel and before.channel.id == target_channel_id:
            return

        if member.id not in data["participants"]:
            data["participants"].append(member.id)
            save_event_data(data)
            print(f"[Event] {member.display_name} ajouté.")

@bot.event
async def on_member_join(member):
    # Liste des IDs des rôles à ajouter
    roles_ids = [1467494034934071377, 1467479393046761556, 1369718575723581550, 1470039631260029120]
    roles_to_add = [member.guild.get_role(rid) for rid in roles_ids if member.guild.get_role(rid)]
    
    if roles_to_add:
        await member.add_roles(*roles_to_add)


# premiere version

## Commande pour créer une carte ID, le joueur va devoir inscrire les information qu'il faut pour créer une ID valide, quand tout sera terminé, le bot va envoyer la carte id dans le salon de validation, et les membres du staff pourront vérifier que les information sont correctes.


# ID des configurations
ID_ROLE_VALIDE = 1468549988052107391
ID_ROLE_NON_VALIDE = 1470039631260029120
ID_SALON_ADMIN = 1371385524505284629

# --- VUE POUR LE STAFF (Accepter / Refuser) ---
class StaffValidationView(discord.ui.View):
    def __init__(self, user_id, user_data):
        super().__init__(timeout=None) # Persistant si nécessaire
        self.user_id = user_id
        self.user_data = user_data

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.green, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        role = guild.get_role(ID_ROLE_VALIDE)
        role2 = guild._remove_role(ID_ROLE_NON_VALIDE)

        if member and role:
            await member.add_roles(role)
            await member.remove_roles(role2)
            # On modifie le message de l'admin pour montrer que c'est traité
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "✅ ID Validée par le Staff"
            await interaction.message.edit(embed=embed, view=None)
            
            # Notifier l'utilisateur en MP (si possible)
            try:
                await member.send(f"Félicitations ! Votre carte d'identité sur **{guild.name}** a été acceptée.")
            except:
                pass
        else:
            await interaction.response.send_message("Erreur : Membre ou rôle introuvable.", ephemeral=True)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.red, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.guild.get_member(self.user_id)
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "❌ ID Refusée"
        await interaction.message.edit(embed=embed, view=None)

        if member:
            try:
                await member.send("Votre demande d'ID a été refusée. Veuillez vérifier vos informations et recommencer.")
            except:
                pass

# --- VUE POUR LE JOUEUR (Confirmation d'envoi) ---
class PlayerConfirmView(discord.ui.View):
    def __init__(self, embed_data):
        super().__init__(timeout=300)
        self.embed_data = embed_data

    @discord.ui.button(label="Envoyer au staff", style=discord.ButtonStyle.primary, emoji="📩")
    async def send_to_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        admin_channel = interaction.guild.get_channel(ID_SALON_ADMIN)
        if admin_channel:
            # On recrée l'embed pour le staff à partir des données
            staff_embed = self.embed_data
            staff_embed.title = "🔔 Nouvelle demande d'ID"
            staff_embed.set_author(name=f"Demandeur : {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            
            view = StaffValidationView(interaction.user.id, self.embed_data)
            await admin_channel.send(embed=staff_embed, view=view)
            
            await interaction.response.edit_message(content="✅ Votre demande a été envoyée au staff pour vérification.", embed=None, view=None)
        else:
            await interaction.response.send_message("Erreur : Salon admin introuvable.", ephemeral=True)

# --- COMMANDE SLASH ---
@bot.tree.command(name="createid", description="Inscrivez vos informations pour créer une ID valide")
@app_commands.choices(sexe=[
    app_commands.Choice(name="Masculin", value="Masculin"),
    app_commands.Choice(name="Féminin", value="Féminin"),
    app_commands.Choice(name="Autre", value="Autre")
])
async def createid(interaction: discord.Interaction, nom: str, prénom: str, sexe: app_commands.Choice[str], nationalité: str, date_de_naiss: str, lieu_de_naissance: str, nom_d_usage: str):
    
    # Vérification du rôle existant
    if any(role.id == ID_ROLE_VALIDE for role in interaction.user.roles):
        await interaction.response.send_message("Vous avez déjà une ID valide.", ephemeral=True)
        return

    # Création de l'embed d'aperçu
    embed = discord.Embed(
        title="🕵️ Vérification de votre ID", 
        description="Voici un aperçu de votre carte. Si tout est bon, cliquez sur le bouton pour l'envoyer au staff.", 
        color=discord.Color.blue()
    )
    embed.add_field(name="Nom", value=nom.upper(), inline=True)
    embed.add_field(name="Prénom", value=prénom.capitalize(), inline=True)
    embed.add_field(name="Sexe", value=sexe.value, inline=True)
    embed.add_field(name="Nationalité", value=nationalité, inline=True)
    embed.add_field(name="Date de naissance", value=date_de_naiss, inline=True)
    embed.add_field(name="Lieu de naissance", value=lieu_de_naissance, inline=True)
    embed.add_field(name="Nom d'usage", value=nom_d_usage, inline=False)
    embed.set_footer(text=f"ID Utilisateur : {interaction.user.id}")

    view = PlayerConfirmView(embed)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


bot.run(os.getenv('DISCORD_TOKEN'))