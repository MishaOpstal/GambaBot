import discord


def create_embed(title: str, description: str = None, color: discord.Color = discord.Color.blue()) -> discord.Embed:
    """Create a standard embed with consistent styling"""
    embed = discord.Embed(title=title, description=description, color=color)
    return embed
