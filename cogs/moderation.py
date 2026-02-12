# cogs/moderation.py
import discord
import time
import io
from discord.ext import commands
from discord import app_commands
# On importe nos outils
from utils import admin_only, load_event_data, save_event_data

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- LISTENER : Arrivée membre ---
    @commands.Cog.listener()
    async def on_member_join(self, member):
        roles_ids = [1467494034934071377, 1467479393046761556, 1369718575723581550, 1470039631260029120]
        roles_to_add = [member.guild.get_role(rid) for rid in roles_ids if member.guild.get_role(rid)]
        if roles_to_add:
            await member.add_roles(*roles_to_add)

    # --- LISTENER : Event Vocal ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return

        data = load_event_data()
        if not data or not data.get("active"): return

        if time.time() - data["start_time"] > 36000: return # Sécurité 10h

        target_channel_id = data["channel_id"]
        
        if after.channel and after.channel.id == target_channel_id:
            if before.channel and before.channel.id == target_channel_id:
                return
            if member.id not in data["participants"]:
                data["participants"].append(member.id)
                save_event_data(data)
                print(f"[Event] {member.display_name} ajouté.")

    # --- COMMANDES ---

    @app_commands.command(name="annonce", description="Faire une annonce structurée")
    @app_commands.describe(titre="Le titre principal", sous_titre="Le sous-titre", paragraphe_1="Premier paragraphe")
    @admin_only
    async def annonce(self, interaction: discord.Interaction, titre: str, sous_titre: str, paragraphe_1: str, paragraphe_2: str = None, paragraphe_3: str = None, image_url: str = None, mention: discord.Member = None):
        CHANNEL_ID = 1468615012263264389
        target_channel = interaction.guild.get_channel(CHANNEL_ID)

        if target_channel is None:
            await interaction.response.send_message(f"❌ Erreur 02 : Salon introuvable.", ephemeral=True)
            return

        contenu_final = f"# 📢 {titre}\n### {sous_titre}\n\n{paragraphe_1}\n\n"
        if paragraphe_2: contenu_final += f"{paragraphe_2}\n\n"
        if paragraphe_3: contenu_final += f"{paragraphe_3}\n\n"
        if mention: contenu_final += f"{mention.mention}\n\n"
        contenu_final += f"_______\n*Transmis par l'État Major de la DMFI*"
        if image_url: contenu_final += f"\n{image_url}"

        try:
            sent_message = await target_channel.send(contenu_final)
            await interaction.response.send_message(f"✅ Annonce publiée !", ephemeral=True)
            try:
                await sent_message.add_reaction("🟩")
                await sent_message.add_reaction("🟧")
                await sent_message.add_reaction("🟥")
            except: pass
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

    @app_commands.command(name="fmi", description="Met à jour les rôles FMI")
    @admin_only
    async def fmi(self, interaction: discord.Interaction, membre1: discord.Member, membre2: discord.Member = None, membre3: discord.Member = None, membre4: discord.Member = None, membre5: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        
        # ID des rôles (à vérifier avec tes IDs réels)
        role_ids = [1401585449587314781, 1230207566794195055, 1369714240948277348] # Ajout
        remove_ids = [1467494034934071377, 1467479393046761556] # Retrait

        membres = [m for m in [membre1, membre2, membre3, membre4, membre5] if m]

        for membre in membres:
            try:
                to_add = [interaction.guild.get_role(rid) for rid in role_ids if interaction.guild.get_role(rid)]
                to_remove = [interaction.guild.get_role(rid) for rid in remove_ids if interaction.guild.get_role(rid)]
                
                await membre.add_roles(*to_add)
                await membre.remove_roles(*to_remove)
            except Exception as e:
                print(f"Erreur FMI sur {membre}: {e}")

        await interaction.followup.send(f"Rôles FMI mis à jour pour {len(membres)} membre(s) !")

    @app_commands.command(name="id", description="Met le rôle ID Valide manuellement")
    @admin_only
    async def id_manual(self, interaction: discord.Interaction, membre1: discord.Member, membre2: discord.Member = None, membre3: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        role_to_add = interaction.guild.get_role(1468549988052107391)
        
        if not role_to_add:
            await interaction.followup.send("❌ Erreur Rôle.", ephemeral=True)
            return

        membres = [m for m in [membre1, membre2, membre3] if m]
        for membre in membres:
            await membre.add_roles(role_to_add)

        await interaction.followup.send(f"✅ Rôle ajouté à {len(membres)} personne(s) !", ephemeral=True)

    @app_commands.command(name="startevent", description="Démarre l'enregistrement vocal")
    @admin_only
    async def startevent(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await interaction.response.defer(ephemeral=True)
        current_data = load_event_data()
        
        if current_data and current_data.get("active"):
            await interaction.followup.send("⚠️ Événement déjà en cours !", ephemeral=True)
            return

        data = {
            "active": True,
            "channel_id": channel.id,
            "start_time": time.time(),
            "participants": [m.id for m in channel.members if not m.bot]
        }
        save_event_data(data)
        
        embed = discord.Embed(title="🎙️ Événement Commencé", description=f"Channel: {channel.mention}", color=discord.Color.green())
        embed.add_field(name="Déjà présents", value=f"{len(data['participants'])} personnes")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="stopevent", description="Arrête l'enregistrement")
    @admin_only
    async def stopevent(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = load_event_data()
        
        if not data or not data.get("active"):
            await interaction.followup.send("❌ Aucun événement.", ephemeral=True)
            return

        # Calculs
        duration_minutes = int((time.time() - data["start_time"]) / 60)
        participant_names = []
        for uid in data["participants"]:
            mem = interaction.guild.get_member(uid)
            participant_names.append(mem.display_name if mem else f"Inconnu ({uid})")

        # Fichier
        file_content = f"Rapport Event\nDurée: {duration_minutes} min\nJoueurs: {len(participant_names)}\n---\n" + "\n".join(participant_names)
        discord_file = discord.File(io.BytesIO(file_content.encode('utf-8')), filename="rapport.txt")

        mod_channel = self.bot.get_channel(1470017104206888990)
        if mod_channel:
            await mod_channel.send(f"📄 **Fin Event**\n⏱️ {duration_minutes} min | 👤 {len(participant_names)} joueurs", file=discord_file)
            await interaction.followup.send("✅ Rapport envoyé.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Salon mod introuvable, voici le fichier :", file=discord_file, ephemeral=True)

        data["active"] = False
        save_event_data(data)


    @app_commands.command(name="valider_candidature", description="Valide une recrue (Réservé au Créateur)")
    @app_commands.describe(recrue="La personne dont la candidature est validée")
    async def valider_candidature(self, interaction: discord.Interaction, recrue: discord.Member):
        # 1. SÉCURITÉ ABSOLUE (Uniquement ton ID)
        ID_AUTORISE = 602585381120114698
        
        if interaction.user.id != ID_AUTORISE:
            await interaction.response.send_message("⛔ **Accès Refusé.** Seul le Créateur peut valider une candidature.", ephemeral=True)
            return

        # 2. On fait patienter (au cas où les rôles mettent du temps)
        await interaction.response.defer()

        # --- CONFIGURATION DES RÔLES (Mets tes IDs ici) ---
        ID_ROLE_A_DONNER = 123456789012345678  # Remplace par l'ID du rôle "Soldat" ou "Recrue"
        ID_ROLE_A_RETIRER = 123456789012345678 # Remplace par l'ID du rôle "Candidat" (si yen a un)
        
        role_give = interaction.guild.get_role(ID_ROLE_A_DONNER)
        role_remove = interaction.guild.get_role(ID_ROLE_A_RETIRER)

        # 3. Attribution des rôles
        try:
            if role_give:
                await recrue.add_roles(role_give)
            
            if role_remove and role_remove in recrue.roles:
                await recrue.remove_roles(role_remove)
            
            # 4. Message de confirmation public
            embed = discord.Embed(
                title="✅ Candidature Validée",
                description=f"Le dossier de {recrue.mention} a été validé par le Haut Commandement.",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=recrue.display_avatar.url)
            await interaction.followup.send(embed=embed)

            # 5. Petit MP au joueur (optionnel)
            try:
                await recrue.send(f"🎉 Félicitations ! Votre candidature sur **{interaction.guild.name}** a été validée. Bienvenue parmi nous.")
            except:
                pass # On ignore si ses MP sont fermés

        except Exception as e:
            await interaction.followup.send(f"⚠️ Une erreur s'est produite lors de l'attribution des rôles : {e}")



async def setup(bot):
    await bot.add_cog(Moderation(bot))