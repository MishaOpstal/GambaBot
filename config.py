import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Bot configuration loaded from environment variables"""

    # Discord
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

    # Web Server
    PORT = int(os.getenv("PORT", 5000))
    DOMAIN = os.getenv("DOMAIN", "localhost")

    # Bot Settings
    DEFAULT_POINTS_EARN_INTERVAL = int(os.getenv("DEFAULT_POINTS_EARN_INTERVAL", 300))  # 5 minutes default
    DEFAULT_POINTS_EARN_RATE = int(os.getenv("DEFAULT_POINTS_EARN_RATE", 50))
    DEFAULT_STARTING_POINTS = int(os.getenv("DEFAULT_STARTING_POINTS", 1000))

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is required in .env file")
        return True


# Validate on import
Config.validate()