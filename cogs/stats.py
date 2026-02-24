import discord
from discord.commands import option

from database import db


class Stats(discord.Cog):
    """Cog for viewing statistics (works in DMs)"""

    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="mystats", description="Show your stats across all servers (works in DMs!)")
    @option("page", int, description="Page number (optional)", min_value=1, required=False, default=1)
    async def show_all_stats(self, ctx: discord.ApplicationContext, page: int = 1):
        """
        Show your stats across all servers (paginated by 10)
        Works in DMs!
        """
        await ctx.defer()

        # Get all guilds the user is in
        user_guilds = []
        for guild in self.bot.guilds:
            if guild.get_member(ctx.author.id):
                user_guilds.append(guild)

        if not user_guilds:
            await ctx.respond("❌ You're not in any servers with this bot!")
            return

        # Paginate
        per_page = 10
        total_pages = (len(user_guilds) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_guilds = user_guilds[start_idx:end_idx]

        # Build stats for each guild
        embed = discord.Embed(
            title=f"📊 Your Stats Across All Servers (Page {page}/{total_pages})",
            color=discord.Color.blue()
        )

        for guild in page_guilds:
            all_points = db.get_all_user_points(guild.id, ctx.author.id)

            if not all_points:
                embed.add_field(
                    name=guild.name,
                    value="No points yet",
                    inline=False
                )
                continue

            # Format points
            lines = []
            total = 0
            for streamer_id, points in all_points.items():
                streamer = guild.get_member(streamer_id)
                if streamer:
                    point_name = db.get_streamer_point_name(guild.id, streamer_id)
                    lines.append(f"• {streamer.display_name}'s {point_name}: {points}")
                    total += points

            if lines:
                embed.add_field(
                    name=f"{guild.name} (Total: {total})",
                    value="\n".join(lines),
                    inline=False
                )

        if total_pages > 1:
            embed.set_footer(text=f"Use /mystats page:{page + 1} to see the next page")

        await ctx.respond(embed=embed)

    @discord.slash_command(name="serverstats", description="Show your stats for a specific server (works in DMs!)")
    @option("server_name", str, description="Server name (required in DMs)", required=False)
    async def show_server_stats(self, ctx: discord.ApplicationContext, server_name: str = None):
        """
        Show your stats for a specific server
        Works in DMs if you provide server name!
        """
        await ctx.defer()

        target_guild = None

        if ctx.guild:
            # Used in a server
            target_guild = ctx.guild
        elif server_name:
            # Used in DM with server name
            for guild in self.bot.guilds:
                if guild.name.lower() == server_name.lower() and guild.get_member(ctx.author.id):
                    target_guild = guild
                    break

            if not target_guild:
                await ctx.respond("❌ Server not found or you're not a member of it!")
                return
        else:
            await ctx.respond("❌ Please provide a server name when using this command in DMs!")
            return

        # Get user's points in this server
        all_points = db.get_all_user_points(target_guild.id, ctx.author.id)

        if not all_points:
            await ctx.respond(f"❌ You don't have any points in **{target_guild.name}** yet!")
            return

        # Format points display
        lines = []
        total = 0
        for streamer_id, points in all_points.items():
            streamer = target_guild.get_member(streamer_id)
            if streamer:
                point_name = db.get_streamer_point_name(target_guild.id, streamer_id)
                lines.append(f"**{streamer.display_name}'s {point_name}**: {points}")
                total += points

        embed = discord.Embed(
            title=f"📊 Your Stats in {target_guild.name}",
            description="\n".join(lines) if lines else "No points yet",
            color=discord.Color.green()
        )
        embed.add_field(name="Total Points", value=str(total), inline=False)

        await ctx.respond(embed=embed)

    @discord.slash_command(name="activebets", description="Show which servers have active predictions (works in DMs!)")
    async def show_active_bets(self, ctx: discord.ApplicationContext):
        """
        Show which servers have active predictions
        Works in DMs!
        """
        await ctx.defer()

        # Get all servers with active predictions
        all_predictions = db.get_all_active_predictions()

        if not all_predictions:
            await ctx.respond("❌ No active predictions in any server!")
            return

        # Filter to only guilds the user is in
        user_active_data = []
        for guild_id, prediction_ids in all_predictions.items():
            guild = self.bot.get_guild(guild_id)
            if guild and guild.get_member(ctx.author.id):
                for pred_id in prediction_ids:
                    prediction = db.get_prediction(guild_id, pred_id)
                    if prediction:
                        user_active_data.append((guild, pred_id, prediction))

        if not user_active_data:
            await ctx.respond("❌ No active predictions in your servers!")
            return

        embed = discord.Embed(
            title="🎲 Active Predictions",
            description=f"Found {len(user_active_data)} active predictions in your servers:",
            color=discord.Color.purple()
        )

        for guild, pred_id, prediction in user_active_data:
            status = "🔒 Closed" if prediction.get('closed') else "✅ Open"

            # Check if user has bet
            user_bet = db.get_bet(guild.id, pred_id, ctx.author.id)
            bet_status = ""
            if user_bet:
                bet_status = f"\n*You bet {user_bet['amount']} on {user_bet['side']}*"

            embed.add_field(
                name=f"{guild.name} - {status} (ID: `{pred_id}`)",
                value=f"**{prediction['question']}**{bet_status}",
                inline=False
            )

        await ctx.respond(embed=embed)

    @discord.slash_command(name="myservers", description="List all servers you share with the bot (works in DMs!)")
    async def show_servers(self, ctx: discord.ApplicationContext):
        """
        List all servers you share with the bot
        Works in DMs!
        """
        await ctx.defer()

        user_guilds = []
        for guild in self.bot.guilds:
            if guild.get_member(ctx.author.id):
                user_guilds.append(guild)

        if not user_guilds:
            await ctx.respond("❌ You're not in any servers with this bot!")
            return

        guild_list = "\n".join([f"• **{guild.name}** ({guild.member_count} members)"
                                for guild in user_guilds])

        embed = discord.Embed(
            title=f"🏠 Your Servers ({len(user_guilds)})",
            description=guild_list,
            color=discord.Color.blue()
        )

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Stats(bot))