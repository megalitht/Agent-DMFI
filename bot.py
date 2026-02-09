import discord
import os
import json
import time
import io
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
async def DMFI(interaction: discord.Interaction):
    await interaction.response.send_message("Voici le lien vers le serveur discord : https://discord.gg/w6BXHah993")


# Pouvoir retouver facilement retrouver le lien du jeu
@bot.tree.command(name="linkbrm", description="affiche le lien vers le jeu Roblox")
async def DMFI(interaction: discord.Interaction):
    await interaction.response.send_message("Voici le lien vers le jeu brm5 : https://www.roblox.com/fr/games/2916899287/Blackhawk-Rescue-Mission-5")

# Pouvoir ban un membre precis
@bot.tree.command(name="ban", description="bannir un membre du serveur")
async def Ban(interaction: discord.Interaction, membre: discord.Member):
    if interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("Ban envoyé !")
        try:
            await membre.send("Tu as été banni.")
        except:
            pass
        await membre.ban()
    else:
        embed = discord.Embed(description="Hop hop hop tu n'as pas les perms !", color=discord.Color.red())
        embed.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif")       
        await interaction.response.send_message(embed=embed)


# Pouvoir kick un membre precis
@bot.tree.command(name="kick", description="exclusion d'un membre du serveur")
async def kick(interaction: discord.Interaction, membre: discord.Member):
    if interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("exclusion envoyer !")
        await membre.send("tu a été expulsé")
        await membre.kick()
    else:
        embed = discord.Embed(description="Hop hop hop tu n'as pas les perms !", color=discord.Color.red())
        embed.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif")
        await interaction.response.send_message(embed=embed)


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
async def annonce(interaction: discord.Interaction, titre: str, sous_titre: str, paragraphe_1: str, paragraphe_2: str = None, paragraphe_3: str = None, image_url: str = None, mention: discord.member = None):
    
    if not interaction.user.guild_permissions.administrator:
        embed_error = discord.Embed(description="Hop hop hop ! Tu n'as pas les perms !", color=discord.Color.red())
        embed_error.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif")
        await interaction.response.send_message(embed=embed_error, ephemeral=True)
        return

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
    if mention: contenu_final += f"{mention}\n\n"
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
async def fmi(interaction: discord.Interaction, membre1: discord.Member, membre2: discord.Member = None, membre3: discord.Member = None, membre4: discord.Member = None, membre5: discord.Member = None):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        embed_error = discord.Embed(description="Hop hop hop ! Tu n'as pas les perms !", color=discord.Color.red())
        embed_error.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif")
        await interaction.followup.send(embed=embed_error, ephemeral=True)
        return
    
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
async def id(interaction: discord.Interaction, membre1: discord.Member, membre2: discord.Member = None, membre3: discord.Member = None):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        embed_error = discord.Embed(description="Hop hop hop ! Tu n'as pas les perms !", color=discord.Color.red())
        embed_error.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif")
        await interaction.followup.send(embed=embed_error, ephemeral=True)
        return
    
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
async def startevent(interaction: discord.Interaction, channel: discord.VoiceChannel):
    await interaction.response.defer(ephemeral=True)
    
    # Vérification permissions
    if not interaction.user.guild_permissions.administrator:
        embed_error = discord.Embed(description="Hop hop hop ! Tu n'as pas les perms !", color=discord.Color.red())
        embed_error.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif")
        await interaction.followup.send(embed=embed_error, ephemeral=True)
        return

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
async def stopevent(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        embed_error = discord.Embed(description="Hop hop hop ! Tu n'as pas les perms !", color=discord.Color.red())
        embed_error.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOGwyYmZlZmFweGg2bWh4Z2x5eDlzNHZ6eW14Z2x5eDlzNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8abAbOrQ9rvLG/giphy.gif")
        await interaction.followup.send(embed=embed_error, ephemeral=True)
        return

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
    # ajouter des role specifique a l'arriver d'un membre
    role = member.guild.get_role(1467494034934071377)
    role = member.guild.get_role(1467479393046761556)
    role = member.guild.get_role(1369718575723581550)
    role = member.guild.get_role(1470039631260029120)
    await member.add_roles(role)
    


# premiere version

## Commande pour créer une carte ID, le joueur va devoir inscrire les information qu'il faut pour créer une ID valide, quand tout sera terminé, le bot va envoyer la carte id dans le salon de validation, et les membres du staff pourront vérifier que les information sont correctes.

# --- 1. Vue pour le Staff (Acceptation/Refus) ---
class StaffValidationView(discord.ui.View):
    def __init__(self, user: discord.Member, role_id: int):
        super().__init__(timeout=None)
        self.user = user
        self.role_id = role_id

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.green, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(self.role_id)
        if role:
            await self.user.add_roles(role)
            await self.user.send(f"✅ Votre carte d'identité a été validée par le staff de **{interaction.guild.name}** !")
            await interaction.response.send_message(f"ID de {self.user.mention} validée par {interaction.user.mention}.", ephemeral=False)
            # On désactive les boutons après traitement
            for btn in self.children: btn.disabled = True
            await interaction.edit_original_response(view=self)
        self.stop()

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.red, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.user.send(f"❌ Votre demande d'ID sur **{interaction.guild.name}** a été refusée. Merci de vérifier vos informations.")
        await interaction.response.send_message(f"ID de {self.user.mention} refusée par {interaction.user.mention}.", ephemeral=False)
        for btn in self.children: btn.disabled = True
        await interaction.edit_original_response(view=self)
        self.stop()

# --- 2. Vue pour le Joueur (Confirmation d'envoi) ---
class PlayerConfirmView(discord.ui.View):
    def __init__(self, embed: discord.Embed, staff_channel_id: int, role_id: int):
        super().__init__(timeout=300)
        self.embed = embed
        self.staff_channel_id = staff_channel_id
        self.role_id = role_id

    @discord.ui.button(label="Envoyer au staff", style=discord.ButtonStyle.primary, emoji="📩")
    async def send_to_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(self.staff_channel_id)
        if channel:
            # On envoie l'ID au staff avec la vue de validation
            view = StaffValidationView(interaction.user, self.role_id)
            await channel.send(content=f"🔔 Nouvelle demande d'ID de {interaction.user.mention} :", embed=self.embed, view=view)
            await interaction.response.send_message("Votre demande a été envoyée au staff. Vous recevrez un message privé une fois validée !", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message("Erreur : Salon de validation introuvable.", ephemeral=True)

# --- 3. La Commande Slash ---

@bot.tree.command(name="createid", description="Remplissez les informations pour votre carte d'identité")
async def createid(
    interaction: discord.Interaction, 
    nom: str, 
    prénom: str, 
    sexe: str, 
    nationalité: str, 
    date_de_naiss: str, 
    lieu_de_naissance: str, 
    nom_d_usage: str
):
    ID_ROLE_VALIDE = 1468549988052107391
    ID_SALON_STAFF = 123456789012345678  # ⚠️ REMPLACEZ PAR L'ID DU SALON STAFF

    # Vérification du rôle
    if any(role.id == ID_ROLE_VALIDE for role in interaction.user.roles):
        await interaction.response.send_message("Vous possédez déjà une ID valide.", ephemeral=True)
        return

    # Création de l'aperçu
    embed = discord.Embed(
        title=f"📇 Carte d'Identité : {nom.upper()} {prénom.capitalize()}",
        description="Informations soumises pour validation :",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(name="Nom d'usage", value=nom_d_usage, inline=False)
    fields = {
        "Nom": nom.upper(), "Prénom": prénom.capitalize(), 
        "Sexe": sexe, "Nationalité": nationalité,
        "Né(e) le": date_de_naiss, "À": lieu_de_naissance
    }
    for name, value in fields.items():
        embed.add_field(name=name, value=value, inline=True)
    
    embed.set_footer(text=f"ID Utilisateur : {interaction.user.id}")

    # Envoi au joueur avec le bouton de confirmation
    view = PlayerConfirmView(embed, ID_SALON_STAFF, ID_ROLE_VALIDE)
    await interaction.response.send_message(
        content="Vérifiez vos informations. Si tout est correct, cliquez sur le bouton ci-dessous pour l'envoyer au staff.", 
        embed=embed, 
        view=view, 
        ephemeral=True
    )

bot.run(os.getenv('DISCORD_TOKEN'))