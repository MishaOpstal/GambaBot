import discord
from discord.ext import commands

from database import db


class Points(commands.Cog):
    """Cog for managing points and streamer settings"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='points', aliases=['pts', 'balance', 'bal'])
    @commands.guild_only()
    async def show_points(self, ctx: commands.Context, member: discord.Member = None):
        """
        Show your or someone else's points

        Usage: $points [@member]
        """
        target = member or ctx.author
        all_points = db.get_all_user_points(ctx.guild.id, target.id)

        if not all_points:
            await ctx.send(f"❌ {target.mention} doesn't have any points yet!")
            return

        # Format points display
        lines = []
        for streamer_id, points in all_points.items():
            streamer = ctx.guild.get_member(streamer_id)
            if not streamer:
                continue

            point_name = db.get_streamer_point_name(ctx.guild.id, streamer_id)
            lines.append(f"**{streamer.display_name}'s {point_name}**: {points}")

        if not lines:
            await ctx.send(f"❌ {target.mention} doesn't have any points yet!")
            return

        embed = discord.Embed(
            title=f"💰 {target.display_name}'s Points",
            description="\n".join(lines),
            color=discord.Color.green()
        )

        await ctx.send(embed=embed)

    @commands.command(name='setpointname', aliases=['setname', 'pointname'])
    @commands.guild_only()
    async def set_point_name(self, ctx: commands.Context, *, name: str):
        """
        Set your custom point name (what others earn watching you)

        Usage: $setpointname <name>
        Example: $setpointname cookies
        """
        if len(name) > 20:
            await ctx.send("❌ Point name must be 20 characters or less!")
            return

        if not name.replace(" ", "").isalnum():
            await ctx.send("❌ Point name can only contain letters, numbers, and spaces!")
            return

        db.set_streamer_point_name(ctx.guild.id, ctx.author.id, name)

        await ctx.send(f"✅ Your point name has been set to **{name}**! "
                       f"People watching your streams will now earn {name}.")

    @commands.command(name='setpointrate', aliases=['setrate', 'rate'])
    @commands.guild_only()
    async def set_point_rate(self, ctx: commands.Context, rate: int):
        """
        Set how many points viewers earn from watching you per interval

        Usage: $setpointrate <amount>
        Example: $setpointrate 100
        """
        if rate < 1 or rate > 1000:
            await ctx.send("❌ Rate must be between 1 and 1000!")
            return

        db.set_streamer_earn_rate(ctx.guild.id, ctx.author.id, rate)

        point_name = db.get_streamer_point_name(ctx.guild.id, ctx.author.id)
        await ctx.send(f"✅ Your earning rate has been set to **{rate} {point_name}** per interval!")

    @commands.command(name='give', aliases=['givepoints'])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def give_points(self, ctx: commands.Context, member: discord.Member,
                          streamer: discord.Member, amount: int):
        """
        Give points to a member (Admin only)

        Usage: $give @member @streamer <amount>
        """
        if amount <= 0:
            await ctx.send("❌ Amount must be positive!")
            return

        current = db.get_user_points(ctx.guild.id, member.id, streamer.id)
        db.set_user_points(ctx.guild.id, member.id, streamer.id, current + amount)

        point_name = db.get_streamer_point_name(ctx.guild.id, streamer.id)

        await ctx.send(f"✅ Gave {member.mention} **{amount} {streamer.display_name}'s {point_name}**!")

    @commands.command(name='take', aliases=['takepoints'])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def take_points(self, ctx: commands.Context, member: discord.Member,
                          streamer: discord.Member, amount: int):
        """
        Take points from a member (Admin only)

        Usage: $take @member @streamer <amount>
        """
        if amount <= 0:
            await ctx.send("❌ Amount must be positive!")
            return

        current = db.get_user_points(ctx.guild.id, member.id, streamer.id)
        new_amount = max(0, current - amount)
        db.set_user_points(ctx.guild.id, member.id, streamer.id, new_amount)

        point_name = db.get_streamer_point_name(ctx.guild.id, streamer.id)

        await ctx.send(f"✅ Took **{amount} {streamer.display_name}'s {point_name}** from {member.mention}!")

    @commands.command(name='leaderboard', aliases=['lb', 'top'])
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context, streamer: discord.Member = None):
        """
        Show the points leaderboard

        Usage: $leaderboard [@streamer]
        If streamer is not specified, shows combined leaderboard
        """
        if streamer:
            # Show leaderboard for specific streamer
            point_name = db.get_streamer_point_name(ctx.guild.id, streamer.id)

            # Get all users with points from this streamer
            user_points = []
            for member in ctx.guild.members:
                if member.bot:
                    continue
                points = db.get_user_points(ctx.guild.id, member.id, streamer.id)
                if points > 0:
                    user_points.append((member, points))

            if not user_points:
                await ctx.send(f"❌ No one has {streamer.display_name}'s {point_name} yet!")
                return

            user_points.sort(key=lambda x: x[1], reverse=True)
            user_points = user_points[:10]  # Top 10

            lines = []
            for i, (member, points) in enumerate(user_points, 1):
                medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
                lines.append(f"{medal} **{member.display_name}**: {points} {point_name}")

            embed = discord.Embed(
                title=f"🏆 Top {streamer.display_name}'s {point_name}",
                description="\n".join(lines),
                color=discord.Color.gold()
            )

            await ctx.send(embed=embed)
        else:
            # Show combined leaderboard (total points across all streamers)
            user_totals = {}

            for member in ctx.guild.members:
                if member.bot:
                    continue
                all_points = db.get_all_user_points(ctx.guild.id, member.id)
                total = sum(all_points.values()) if all_points else 0
                if total > 0:
                    user_totals[member] = total

            if not user_totals:
                await ctx.send("❌ No one has any points yet!")
                return

            sorted_users = sorted(user_totals.items(), key=lambda x: x[1], reverse=True)[:10]

            lines = []
            for i, (member, total) in enumerate(sorted_users, 1):
                medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
                lines.append(f"{medal} **{member.display_name}**: {total} total points")

            embed = discord.Embed(
                title="🏆 Total Points Leaderboard",
                description="\n".join(lines),
                color=discord.Color.gold()
            )

            await ctx.send(embed=embed)

    @commands.command(name='streamerinfo', aliases=['sinfo'])
    @commands.guild_only()
    async def streamer_info(self, ctx: commands.Context, streamer: discord.Member = None):
        """
        Show streamer's point settings

        Usage: $streamerinfo [@streamer]
        """
        target = streamer or ctx.author

        point_name = db.get_streamer_point_name(ctx.guild.id, target.id)
        earn_rate = db.get_streamer_earn_rate(ctx.guild.id, target.id)

        from config import Config

        embed = discord.Embed(
            title=f"📊 {target.display_name}'s Streamer Info",
            color=discord.Color.blue()
        )
        embed.add_field(name="Point Name", value=point_name, inline=True)
        embed.add_field(name="Earning Rate", value=f"{earn_rate} per {Config.POINTS_EARN_INTERVAL}s", inline=True)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Points(bot))
