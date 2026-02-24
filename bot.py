import logging

import discord
from discord.ext import commands

from config import Config
from database import db

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PredictionBot(commands.Bot):
    """Main bot class for the prediction and streaming points system"""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        intents.guilds = True

        super().__init__(
            command_prefix='$',
            intents=intents,
            case_insensitive=True,
            help_command=commands.DefaultHelpCommand()
        )

    async def setup_hook(self):
        """Load cogs during bot setup"""
        cogs = [
            'cogs.predictions',
            'cogs.points',
            'cogs.streams',
            'cogs.stats'
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")

    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info(f'Bot logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Connected to {len(self.guilds)} guilds')

        # Check Redis connection
        if db.ping():
            logger.info("Redis connection successful")
        else:
            logger.error("Redis connection failed!")

        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="streams | $help"
            )
        )

    @staticmethod
    async def on_guild_join(guild: discord.Guild):
        """Called when bot joins a new guild"""
        logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")

    @staticmethod
    async def on_guild_remove(guild: discord.Guild):
        """Called when bot leaves a guild"""
        logger.info(f"Left guild: {guild.name} (ID: {guild.id})")

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global error handler"""
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"❌ You don't have permission to use this command.")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: {error.param.name}")
            return

        if isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Invalid argument provided.")
            return

        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(f"❌ This command cannot be used in DMs.")
            return

        # Log unexpected errors
        logger.error(f"Unexpected error in command {ctx.command}: {error}", exc_info=error)
        await ctx.send(f"❌ An unexpected error occurred. Please try again later.")


def main():
    """Main entry point"""
    bot = PredictionBot()

    try:
        bot.run(Config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=e)


if __name__ == "__main__":
    main()
