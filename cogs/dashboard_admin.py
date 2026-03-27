# cogs/dashboard.py
import discord
from discord.ext import commands
from discord import app_commands
from utils import admin_only
from database import set_server_config, get_server_config
import json

class AdmDashboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

# --- COMPOSANTS DE BASE ---
class ConfigRoleSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id, db_key, placeholder, max_values=1, row=1):
        super().__init__(placeholder=placeholder, min_values=1, max_values=max_values, row=row)
        self.guild_id = guild_id
        self.db_key = db_key
    async def callback(self, interaction: discord.Interaction):
        value = ",".join(str(r.id) for r in self.values) if self.max_values > 1 else self.values[0].id
        set_server_config(self.guild_id, self.db_key, value)
        await interaction.response.send_message("✅ Sauvegardé ! **Relancez la catégorie pour voir les changements.**", ephemeral=True)

class ConfigChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id, db_key, placeholder, channel_types, row=1):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, channel_types=channel_types, row=row)
        self.guild_id = guild_id
        self.db_key = db_key
    async def callback(self, interaction: discord.Interaction):
        set_server_config(self.guild_id, self.db_key, self.values[0].id)
        await interaction.response.send_message("✅ Sauvegardé ! **Relancez la catégorie.**", ephemeral=True)

class ToggleModuleButton(discord.ui.Button):
    def __init__(self, guild_id, module_key, is_active, row=4):
        self.guild_id = guild_id
        self.module_key = module_key
        self.is_active = is_active
        label = "🔴 Désactiver module" if is_active else "🟢 Activer module"
        style = discord.ButtonStyle.red if is_active else discord.ButtonStyle.green
        super().__init__(label=label, style=style, row=row)
    async def callback(self, interaction: discord.Interaction):
        new_state = 0 if self.is_active else 1
        set_server_config(self.guild_id, self.module_key, new_state)
        await interaction.response.send_message("🔄 Module mis à jour ! **Relancez la catégorie.**", ephemeral=True)

class ResetConfigButton(discord.ui.Button):
    def __init__(self, guild_id, db_key, label, row=4):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, emoji="🗑️", row=row)
        self.guild_id = guild_id
        self.db_key = db_key
    async def callback(self, interaction: discord.Interaction):
        set_server_config(self.guild_id, self.db_key, None)
        await interaction.response.send_message(f"🗑️ {label} effacé ! **Relancez la catégorie.**", ephemeral=True)

# --- MODALS ET BOUTONS SPÉCIFIQUES ---
class WebhookModal(discord.ui.Modal, title="Configuration du Webhook"):
    name_input = discord.ui.TextInput(label="Nom du Bot (Say)", placeholder="Ex: Agent de Police", required=True)
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
    async def on_submit(self, interaction: discord.Interaction):
        set_server_config(self.guild_id, "webhook_name", self.name_input.value)
        await interaction.response.send_message(f"✅ Nom du webhook défini sur : **{self.name_input.value}**", ephemeral=True)

class ConfigWebhookButton(discord.ui.Button):
    def __init__(self, guild_id, row=1):
        super().__init__(label="Configurer Nom Webhook", style=discord.ButtonStyle.primary, emoji="🤖", row=row)
        self.guild_id = guild_id
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WebhookModal(self.guild_id))

class CodeServeurModal(discord.ui.Modal, title="Configuration des Codes VIP (Max 5)"):
    code_1 = discord.ui.TextInput(label="Serveur n°1", placeholder="Ex: ABC-123", required=False)
    code_2 = discord.ui.TextInput(label="Serveur n°2", placeholder="Ex: DEF-456", required=False)
    code_3 = discord.ui.TextInput(label="Serveur n°3", placeholder="Ex: GHI-789", required=False)
    code_4 = discord.ui.TextInput(label="Serveur n°4", placeholder="Ex: JKL-012", required=False)
    code_5 = discord.ui.TextInput(label="Serveur n°5", placeholder="Ex: MNO-345", required=False)

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        # On regroupe les 5 codes dans une liste
        codes = [
            self.code_1.value.strip(),
            self.code_2.value.strip(),
            self.code_3.value.strip(),
            self.code_4.value.strip(),
            self.code_5.value.strip()
        ]
        set_server_config(self.guild_id, "code_serveur", json.dumps(codes))
        
        actifs = sum(1 for c in codes if c)
        await interaction.response.send_message(f"✅ Configuration sauvegardée : **{actifs}/5** serveurs ouverts.", ephemeral=True)

class ConfigCodeButton(discord.ui.Button):
    def __init__(self, guild_id, row=2):
        super().__init__(label="Configurer Code VIP", style=discord.ButtonStyle.success, emoji="🎮", row=row)
        self.guild_id = guild_id
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CodeServeurModal(self.guild_id))

class SalaryConfigModal(discord.ui.Modal, title="Configurer un salaire horaire"):
    role_id_input = discord.ui.TextInput(label="ID du Rôle Discord", placeholder="Ex: 123456789012345678", required=True)
    amount_input = discord.ui.TextInput(label="Montant du salaire ($)", placeholder="Ex: 500", required=True)
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
    async def on_submit(self, interaction: discord.Interaction):
        config = get_server_config(self.guild_id)
        salaries = json.loads(config.get("salary_roles", "{}") or "{}")
        if len(salaries) >= 10 and self.role_id_input.value not in salaries:
            return await interaction.response.send_message("❌ Limite de 10 salaires atteinte.", ephemeral=True)
        try:
            role_id_str = str(int(self.role_id_input.value))
            amount = int(self.amount_input.value)
            salaries[role_id_str] = amount
            set_server_config(self.guild_id, "salary_roles", json.dumps(salaries))
            await interaction.response.send_message(f"✅ Salaire ajouté : <@&{role_id_str}> -> {amount}$/h", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ L'ID et le montant doivent être des nombres.", ephemeral=True)

class AddSalaryButton(discord.ui.Button):
    def __init__(self, guild_id, row=2):
        super().__init__(label="Ajouter/Modifier Salaire", style=discord.ButtonStyle.success, emoji="💰", row=row)
        self.guild_id = guild_id
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SalaryConfigModal(self.guild_id))

class PrixModal(discord.ui.Modal):
    def __init__(self, guild_id, db_key, nom_permis):
        super().__init__(title=f"Prix Permis {nom_permis}")
        self.guild_id = guild_id
        self.db_key = db_key
        self.prix_input = discord.ui.TextInput(label="Nouveau prix ($)", placeholder="Ex: 1500", required=True)
        self.add_item(self.prix_input)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            nouveau_prix = int(self.prix_input.value)
            set_server_config(self.guild_id, self.db_key, nouveau_prix)
            await interaction.response.send_message(f"✅ Prix mis à jour : {nouveau_prix}$", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Le prix doit être un nombre !", ephemeral=True)

class ConfigPrixButton(discord.ui.Button):
    def __init__(self, guild_id, db_key, nom_permis, row=1):
        super().__init__(label=f"Modifier Prix {nom_permis}", style=discord.ButtonStyle.primary, emoji="💳", row=row)
        self.guild_id = guild_id
        self.db_key = db_key
        self.nom_permis = nom_permis
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PrixModal(self.guild_id, self.db_key, self.nom_permis))

class RGESelect(discord.ui.Select):
    def __init__(self, guild_id, row=3):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label="RGE Serveur 1", value="0", emoji="⚙️"),
            discord.SelectOption(label="RGE Serveur 2", value="1", emoji="⚙️"),
            discord.SelectOption(label="RGE Serveur 3", value="2", emoji="⚙️"),
            discord.SelectOption(label="RGE Serveur 4", value="3", emoji="⚙️"),
            discord.SelectOption(label="RGE Serveur 5", value="4", emoji="⚙️")
        ]
        super().__init__(placeholder="Activer/Désactiver RGE...", options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        config = get_server_config(self.guild_id)
        rge_data = config.get("rge_serveur", "[0, 0, 0, 0, 0]")
        try:
            rge_list = json.loads(rge_data)
        except json.JSONDecodeError:
            rge_list = [0, 0, 0, 0, 0]

        while len(rge_list) < 5: rge_list.append(0)

        index = int(self.values[0])
        rge_list[index] = 1 if rge_list[index] == 0 else 0 # Bascule ON/OFF

        set_server_config(self.guild_id, "rge_serveur", json.dumps(rge_list))
        etat = "🟢 ACTIVÉ" if rge_list[index] == 1 else "🔴 DÉSACTIVÉ"
        await interaction.response.send_message(f"✅ RGE du Serveur {index + 1} mis à jour : **{etat}**", ephemeral=True)

# ================= DASHBOARD ADMIN / MODERATION =================
class AdminCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Modération & Accueil", emoji="📢", value="announces"),
            discord.SelectOption(label="Système FMI", emoji="🎖️", value="fmi"),
            discord.SelectOption(label="Événements", emoji="🎙️", value="event"),
            discord.SelectOption(label="Autres Configurations", emoji="⚙️", value="autres")
        ]
        super().__init__(placeholder="Menu Administration...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view = discord.ui.View(timeout=None)
        view.add_item(AdminCategorySelect()) 
        g_id = interaction.guild.id
        config = get_server_config(g_id)
        val = self.values[0]

        def get_role_mentions(key):
            v = config.get(key)
            return ", ".join([f"<@&{r}>" for r in str(v).split(",")]) if v else "Aucun"
        def get_channel_mention(key):
            v = config.get(key)
            return f"<#{v}>" if v else "Aucun"

        if val == "announces":
            is_act = config.get("module_mod_active", 1)
            desc = f"**État:** {'🟢 ACTIVÉ' if is_act else '🔴 DÉSACTIVÉ'}\n**Salon Annonces:** {get_channel_mention('salon_annonce_id')}\n**Auto-rôles:** {get_role_mentions('autoroles')}"
            embed = discord.Embed(title="📢 Modération & Accueil", description=desc, color=discord.Color.green())
            view.add_item(ConfigChannelSelect(g_id, "salon_annonce_id", "Salon Annonces", [discord.ChannelType.text, discord.ChannelType.news], row=1))
            view.add_item(ConfigRoleSelect(g_id, "autoroles", "Auto-rôles (Max 5)", 5, row=2))
            view.add_item(ToggleModuleButton(g_id, "module_mod_active", is_act, row=4))
            view.add_item(ResetConfigButton(g_id, "salon_annonce_id", "Salon", row=4))
            view.add_item(ResetConfigButton(g_id, "autoroles", "Auto-rôles", row=4))
            
        elif val == "fmi":
            is_act = config.get("module_fmi_active", 1)
            desc = f"**État:** {'🟢 ACTIVÉ' if is_act else '🔴 DÉSACTIVÉ'}\n**Ajout:** {get_role_mentions('fmi_add_roles')}\n**Retrait:** {get_role_mentions('fmi_remove_roles')}"
            embed = discord.Embed(title="🎖️ Système FMI", description=desc, color=discord.Color.gold())
            view.add_item(ConfigRoleSelect(g_id, "fmi_add_roles", "Rôles à AJOUTER", 5, row=1))
            view.add_item(ConfigRoleSelect(g_id, "fmi_remove_roles", "Rôles à RETIRER", 5, row=2))
            view.add_item(ToggleModuleButton(g_id, "module_fmi_active", is_act, row=4))
            view.add_item(ResetConfigButton(g_id, "fmi_add_roles", "Ajouts", row=4))
            view.add_item(ResetConfigButton(g_id, "fmi_remove_roles", "Retraits", row=4))
            
        elif val == "event":
            is_act = config.get("module_event_active", 1)
            desc = f"**État:** {'🟢 ACTIVÉ' if is_act else '🔴 DÉSACTIVÉ'}\n**Vocal:** {get_channel_mention('event_voice_id')}\n**Rapports:** {get_channel_mention('event_report_id')}"
            embed = discord.Embed(title="🎙️ Événements", description=desc, color=discord.Color.purple())
            view.add_item(ConfigChannelSelect(g_id, "event_voice_id", "Salon Vocal", [discord.ChannelType.voice], row=1))
            view.add_item(ConfigChannelSelect(g_id, "event_report_id", "Salon Rapports", [discord.ChannelType.text], row=2))
            view.add_item(ToggleModuleButton(g_id, "module_event_active", is_act, row=4))
            view.add_item(ResetConfigButton(g_id, "event_voice_id", "Vocal", row=4))
            view.add_item(ResetConfigButton(g_id, "event_report_id", "Rapports", row=4))

        elif val == "autres":
            nom_bot = config.get("webhook_name", "Agent DMFI")
            code_vip = config.get("code_serveur", "Aucun")
            desc = f"**Nom Bot (Say):** {nom_bot}\n**Code Serveur:** {code_vip}"
            embed = discord.Embed(title="⚙️ Autres Configurations", description=desc, color=discord.Color.light_grey())
            view.add_item(ConfigWebhookButton(g_id, row=1))
            view.add_item(ConfigCodeButton(g_id, row=2))
            view.add_item(RGESelect(g_id, row=3)) # <--- LIGNE AJOUTÉE
            view.add_item(ResetConfigButton(g_id, "webhook_name", "Nom Bot", row=4))
            view.add_item(ResetConfigButton(g_id, "code_serveur", "Code Serveur", row=4))
    


        await interaction.response.edit_message(embed=embed, view=view)

# ================= DASHBOARD RP / ECONOMIE =================
class RPCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Identité (Cartes)", emoji="🎭", value="id"),
            discord.SelectOption(label="Économie (Général)", emoji="💼", value="eco"),
            discord.SelectOption(label="Auto-École : Voiture", emoji="🚗", value="permis_v"),
            discord.SelectOption(label="Auto-École : Poids Lourd", emoji="🚚", value="permis_pl"),
            discord.SelectOption(label="Auto-École : Hélicoptère", emoji="🚁", value="permis_h")
        ]
        super().__init__(placeholder="Menu RP & Économie...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view = discord.ui.View(timeout=None)
        view.add_item(RPCategorySelect()) 
        g_id = interaction.guild.id
        config = get_server_config(g_id)
        val = self.values[0]

        def get_role_mentions(key):
            v = config.get(key)
            return ", ".join([f"<@&{r}>" for r in str(v).split(",")]) if v else "Aucun"
        def get_channel_mention(key):
            v = config.get(key)
            return f"<#{v}>" if v else "Aucun"

        if val == "id":
            is_act = config.get("module_rp_active", 1)
            desc = f"**État:** {'🟢 ACTIVÉ' if is_act else '🔴 DÉSACTIVÉ'}\n**ID Valide:** {get_role_mentions('role_valide_id')}\n**ID Non-Valide:** {get_role_mentions('role_non_valide_id')}\n**Admin:** {get_channel_mention('salon_admin_id')}"
            embed = discord.Embed(title="🎭 Système Identité", description=desc, color=discord.Color.blue())
            view.add_item(ConfigRoleSelect(g_id, "role_valide_id", "Rôle Valide", 1, row=1))
            view.add_item(ConfigRoleSelect(g_id, "role_non_valide_id", "Rôle Non-Valide", 1, row=2))
            view.add_item(ConfigChannelSelect(g_id, "salon_admin_id", "Salon Admin", [discord.ChannelType.text], row=3))
            view.add_item(ToggleModuleButton(g_id, "module_rp_active", is_act, row=4))
            view.add_item(ResetConfigButton(g_id, "role_valide_id", "Valide", row=4))
            view.add_item(ResetConfigButton(g_id, "role_non_valide_id", "Non-Valide", row=4))

        elif val == "eco":
            is_act = config.get("module_citoyen_active", 1)
            salaries = json.loads(config.get("salary_roles", "{}") or "{}")
            desc = f"**État:** {'🟢 ACTIVÉ' if is_act else '🔴 DÉSACTIVÉ'}\n**Police:** {get_role_mentions('role_police_id')}\n\n**Salaires ({len(salaries)}/10) :**\n"
            if not salaries:
                desc += "*Aucun salaire configuré.*\n"
            else:
                for r, m in salaries.items(): desc += f"• <@&{r}> : {m}$/h\n"
            

async def setup(bot):
    await bot.add_cog(AdmDashboardCog(bot))