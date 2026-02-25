import logging

import discord

from config import Config
from database import db

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PredictionBot(discord.Bot):
    """Main bot class for the prediction and streaming points system"""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        intents.guilds = True

        super().__init__(intents=intents)

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
                name="streams | Use /help"
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

    async def on_application_command_error(self, ctx: discord.ApplicationContext, error: Exception):
        """Global error handler for slash commands"""
        if isinstance(error, discord.CheckFailure):
            await ctx.respond("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if isinstance(error, discord.ApplicationCommandInvokeError):
            error = error.original

        # Log unexpected errors
        logger.error(f"Unexpected error in command {ctx.command}: {error}", exc_info=error)
        await ctx.respond("❌ An unexpected error occurred. Please try again later.", ephemeral=True)


def main():
    """Main entry point"""
    bot = PredictionBot()

    # Load cogs
    cogs = [
        'cogs.predictions',
        'cogs.points',
        'cogs.streams',
        'cogs.stats'
    ]

    for cog in cogs:
        try:
            bot.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        except Exception as e:
            logger.error(f"Failed to load cog {cog}: {e}")

    # Start web server in separate thread
    from web_server import init_web_server, run_web_server
    import threading

    init_web_server(bot)
    web_thread = threading.Thread(
        target=run_web_server,
        kwargs={'host': '0.0.0.0', 'port': Config.PORT},
        daemon=True
    )
    web_thread.start()
    logger.info(f"Web server started on http://0.0.0.0:{Config.PORT}")

    try:
        bot.run(Config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=e)


if __name__ == "__main__":
    main()