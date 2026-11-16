import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from data import SERVEUR_PRINCIPAL_ID, COMMANDES_HORS_PRINCIPAL

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

MESSAGE_HORS_PRINCIPAL = "❌ Cette commande de l'Agent DMFI ne s'utilise que sur le serveur principal."


def commande_autorisee(guild_id: int | None, nom_commande: str | None) -> bool:
    """
    Le bot est présent sur plusieurs serveurs, mais le recensement ne se gère que depuis le
    serveur principal : ailleurs, seules les commandes de COMMANDES_HORS_PRINCIPAL passent.
    (guild_id None = message privé : laissé tel quel.)
    """
    if guild_id is None or guild_id == SERVEUR_PRINCIPAL_ID:
        return True
    return nom_commande in COMMANDES_HORS_PRINCIPAL


class ArbreDMFI(app_commands.CommandTree):
    """Bloque les commandes slash lancées depuis un serveur secondaire."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        commande = interaction.command
        nom = commande.root_parent.name if getattr(commande, "root_parent", None) else getattr(commande, "name", None)
        if commande_autorisee(interaction.guild_id, nom):
            return True
        if interaction.type is discord.InteractionType.application_command:
            await interaction.response.send_message(MESSAGE_HORS_PRINCIPAL, ephemeral=True)
        return False


class DMFIBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Indispensable pour résoudre l'ID Discord -> Membre

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            tree_cls=ArbreDMFI,
        )
        # Même règle pour les commandes tapées avec le préfixe « ! »
        self.add_check(self._verifier_serveur)

    @staticmethod
    def _verifier_serveur(ctx: commands.Context) -> bool:
        nom = ctx.command.root_parent.name if ctx.command and ctx.command.root_parent else getattr(ctx.command, "name", None)
        return commande_autorisee(ctx.guild.id if ctx.guild else None, nom)

    async def setup_hook(self):
        # Chargement automatique des Cogs présents dans le dossier ./cogs
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and not filename.startswith("_"):
                await self.load_extension(f"cogs.{filename[:-3]}")
                print(f"[COG] {filename} chargé avec succès.")

        # Synchronisation des commandes Slash (/)
        await self.tree.sync()
        print("[SLASH] Commandes synchronisées.")

    async def on_ready(self):
        print(f"[BOT] Connecté en tant que {self.user} (ID: {self.user.id})")
        print("------")

async def main():
    bot = DMFIBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
