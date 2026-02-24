import discord
from discord.ext import commands

from database import db


class Stats(commands.Cog):
    """Cog for viewing statistics (works in DMs)"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='mystats', aliases=['stats', 'allstats'])
    async def show_all_stats(self, ctx: commands.Context, page: int = 1):
        """
        Show your stats across all servers (paginated by 10)
        Works in DMs!

        Usage: $mystats [page]
        """
        # Get all guilds the user is in
        user_guilds = []
        for guild in self.bot.guilds:
            if guild.get_member(ctx.author.id):
                user_guilds.append(guild)

        if not user_guilds:
            await ctx.send("❌ You're not in any servers with this bot!")
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
            embed.set_footer(text=f"Use $mystats {page + 1} to see the next page")

        await ctx.send(embed=embed)

    @commands.command(name='serverstats', aliases=['guildstats'])
    async def show_server_stats(self, ctx: commands.Context, *, server_name: str = None):
        """
        Show your stats for a specific server
        Works in DMs if you provide server name!

        Usage: $serverstats [server name]
        If used in a server, shows that server's stats
        If used in DM, requires server name
        """
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
                await ctx.send("❌ Server not found or you're not a member of it!")
                return
        else:
            await ctx.send("❌ Please provide a server name when using this command in DMs!")
            return

        # Get user's points in this server
        all_points = db.get_all_user_points(target_guild.id, ctx.author.id)

        if not all_points:
            await ctx.send(f"❌ You don't have any points in **{target_guild.name}** yet!")
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

        await ctx.send(embed=embed)

    @commands.command(name='activebets', aliases=['bets', 'predictions'])
    async def show_active_bets(self, ctx: commands.Context):
        """
        Show which servers have active predictions
        Works in DMs!

        Usage: $activebets
        """
        # Get all servers with active predictions
        active_guild_ids = db.get_all_active_predictions()

        if not active_guild_ids:
            await ctx.send("❌ No active predictions in any server!")
            return

        # Filter to only guilds the user is in
        user_active_guilds = []
        for guild_id in active_guild_ids:
            guild = self.bot.get_guild(guild_id)
            if guild and guild.get_member(ctx.author.id):
                prediction = db.get_prediction(guild_id)
                user_active_guilds.append((guild, prediction))

        if not user_active_guilds:
            await ctx.send("❌ No active predictions in your servers!")
            return

        embed = discord.Embed(
            title="🎲 Active Predictions",
            description=f"Predictions in {len(user_active_guilds)} of your servers:",
            color=discord.Color.purple()
        )

        for guild, prediction in user_active_guilds:
            status = "🔒 Closed" if prediction.get('closed') else "✅ Open"

            # Check if user has bet
            user_bet = db.get_bet(guild.id, ctx.author.id)
            bet_status = ""
            if user_bet:
                bet_status = f"\n*You bet {user_bet['amount']} on {user_bet['side']}*"

            embed.add_field(
                name=f"{guild.name} - {status}",
                value=f"**{prediction['question']}**{bet_status}",
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.command(name='myservers', aliases=['servers'])
    async def show_servers(self, ctx: commands.Context):
        """
        List all servers you share with the bot
        Works in DMs!

        Usage: $myservers
        """
        user_guilds = []
        for guild in self.bot.guilds:
            if guild.get_member(ctx.author.id):
                user_guilds.append(guild)

        if not user_guilds:
            await ctx.send("❌ You're not in any servers with this bot!")
            return

        guild_list = "\n".join([f"• **{guild.name}** ({guild.member_count} members)"
                                for guild in user_guilds])

        embed = discord.Embed(
            title=f"🏠 Your Servers ({len(user_guilds)})",
            description=guild_list,
            color=discord.Color.blue()
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))
