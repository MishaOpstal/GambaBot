import discord
from discord.commands import SlashCommandGroup, option

from database import db


class Points(discord.Cog):
    """Cog for managing points and streamer settings"""

    def __init__(self, bot):
        self.bot = bot

    points = SlashCommandGroup("points", "Points and streamer commands")

    @points.command(name="show", description="Show your or someone else's points")
    @option("member", discord.Member, description="Member to check (optional)", required=False)
    async def show_points(self, ctx: discord.ApplicationContext, member: discord.Member = None):
        """Show your or someone else's points"""
        await ctx.defer()

        target = member or ctx.author
        all_points = db.get_all_user_points(ctx.guild.id, target.id)

        if not all_points:
            await ctx.respond(f"❌ {target.mention} doesn't have any points yet!")
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
            await ctx.respond(f"❌ {target.mention} doesn't have any points yet!")
            return

        embed = discord.Embed(
            title=f"💰 {target.display_name}'s Points",
            description="\n".join(lines),
            color=discord.Color.green()
        )

        await ctx.respond(embed=embed)

    @points.command(name="setname", description="Set your custom point name")
    @option("name", str, description="The name for your points (max 20 characters)")
    async def set_point_name(self, ctx: discord.ApplicationContext, name: str):
        """Set your custom point name (what others earn watching you)"""
        await ctx.defer(ephemeral=True)

        if len(name) > 20:
            await ctx.respond("❌ Point name must be 20 characters or less!", ephemeral=True)
            return

        if not name.replace(" ", "").isalnum():
            await ctx.respond("❌ Point name can only contain letters, numbers, and spaces!", ephemeral=True)
            return

        db.set_streamer_point_name(ctx.guild.id, ctx.author.id, name)

        await ctx.respond(
            f"✅ Your point name has been set to **{name}**! "
            f"People watching your streams will now earn {name}.",
            ephemeral=True
        )

    @points.command(name="setrate", description="Set how many points viewers earn per interval")
    @option("rate", int, description="Points per interval (1-1000)", min_value=1, max_value=1000)
    async def set_point_rate(self, ctx: discord.ApplicationContext, rate: int):
        """Set how many points viewers earn from watching you per interval"""
        await ctx.defer(ephemeral=True)

        db.set_streamer_earn_rate(ctx.guild.id, ctx.author.id, rate)

        point_name = db.get_streamer_point_name(ctx.guild.id, ctx.author.id)
        interval = db.get_streamer_earn_interval(ctx.guild.id, ctx.author.id)
        await ctx.respond(
            f"✅ Your earning rate has been set to **{rate} {point_name}** per {interval}s!",
            ephemeral=True
        )

    @points.command(name="setinterval", description="Set how often viewers earn points")
    @option("interval", int, description="Interval in seconds (60-3600)", min_value=60, max_value=3600)
    async def set_point_interval(self, ctx: discord.ApplicationContext, interval: int):
        """Set how often viewers earn points from watching you (in seconds)"""
        await ctx.defer(ephemeral=True)

        db.set_streamer_earn_interval(ctx.guild.id, ctx.author.id, interval)

        point_name = db.get_streamer_point_name(ctx.guild.id, ctx.author.id)
        rate = db.get_streamer_earn_rate(ctx.guild.id, ctx.author.id)
        await ctx.respond(
            f"✅ Your earning interval has been set to **{interval}s**. "
            f"Viewers will now earn {rate} {point_name} every {interval} seconds.",
            ephemeral=True
        )

    @points.command(name="give", description="Give points to a member (Admin only)")
    @option("member", discord.Member, description="Member to give points to")
    @option("streamer", discord.Member, description="Which streamer's points to give")
    @option("amount", int, description="Amount to give", min_value=1)
    @discord.default_permissions(administrator=True)
    async def give_points(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member,
        streamer: discord.Member,
        amount: int
    ):
        """Give points to a member (Admin only)"""
        await ctx.defer(ephemeral=True)

        current = db.get_user_points(ctx.guild.id, member.id, streamer.id)
        db.set_user_points(ctx.guild.id, member.id, streamer.id, current + amount)

        point_name = db.get_streamer_point_name(ctx.guild.id, streamer.id)

        await ctx.respond(
            f"✅ Gave {member.mention} **{amount} {streamer.display_name}'s {point_name}**!",
            ephemeral=True
        )

    @points.command(name="take", description="Take points from a member (Admin only)")
    @option("member", discord.Member, description="Member to take points from")
    @option("streamer", discord.Member, description="Which streamer's points to take")
    @option("amount", int, description="Amount to take", min_value=1)
    @discord.default_permissions(administrator=True)
    async def take_points(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member,
        streamer: discord.Member,
        amount: int
    ):
        """Take points from a member (Admin only)"""
        await ctx.defer(ephemeral=True)

        current = db.get_user_points(ctx.guild.id, member.id, streamer.id)
        new_amount = max(0, current - amount)
        db.set_user_points(ctx.guild.id, member.id, streamer.id, new_amount)

        point_name = db.get_streamer_point_name(ctx.guild.id, streamer.id)

        await ctx.respond(
            f"✅ Took **{amount} {streamer.display_name}'s {point_name}** from {member.mention}!",
            ephemeral=True
        )

    @discord.slash_command(name="leaderboard", description="Show the points leaderboard")
    @option("streamer", discord.Member, description="Show leaderboard for specific streamer (optional)", required=False)
    async def leaderboard(self, ctx: discord.ApplicationContext, streamer: discord.Member = None):
        """Show the points leaderboard"""
        await ctx.defer()

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
                await ctx.respond(f"❌ No one has {streamer.display_name}'s {point_name} yet!")
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

            await ctx.respond(embed=embed)
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
                await ctx.respond("❌ No one has any points yet!")
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

            await ctx.respond(embed=embed)

    @discord.slash_command(name="streamerinfo", description="Show streamer's point settings")
    @option("streamer", discord.Member, description="Streamer to check (optional)", required=False)
    async def streamer_info(self, ctx: discord.ApplicationContext, streamer: discord.Member = None):
        """Show streamer's point settings"""
        await ctx.defer()

        target = streamer or ctx.author

        point_name = db.get_streamer_point_name(ctx.guild.id, target.id)
        earn_rate = db.get_streamer_earn_rate(ctx.guild.id, target.id)
        earn_interval = db.get_streamer_earn_interval(ctx.guild.id, target.id)

        embed = discord.Embed(
            title=f"📊 {target.display_name}'s Streamer Info",
            color=discord.Color.blue()
        )
        embed.add_field(name="Point Name", value=point_name, inline=True)
        embed.add_field(name="Earning Rate", value=f"{earn_rate} per {earn_interval}s", inline=True)

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Points(bot))