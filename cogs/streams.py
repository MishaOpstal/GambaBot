import discord
from discord.ext import tasks
from discord.commands import option
from database import db
from config import Config
import logging

logger = logging.getLogger(__name__)


class Streams(discord.Cog):
    """Cog for tracking stream viewers and awarding points"""

    def __init__(self, bot):
        self.bot = bot
        self.award_points.start()

    def cog_unload(self):
        self.award_points.cancel()

    @tasks.loop(seconds=60)
    async def award_points(self):
        """Award points to viewers at regular intervals"""
        import time
        now = int(time.time())
        for guild in self.bot.guilds:
            try:
                await self._award_points_for_guild(guild, now)
            except Exception as e:
                logger.error(f"Error awarding points in guild {guild.id}: {e}")

    @award_points.before_loop
    async def before_award_points(self):
        await self.bot.wait_until_ready()

    @staticmethod
    async def _award_points_for_guild(guild: discord.Guild, now: int):
        """Award points to all viewers in a guild"""
        # Track current streamers
        current_streamers = set()

        # Check all members for streaming activity
        for member in guild.members:
            if member.bot:
                continue

            # Check if member is streaming
            is_streaming = False
            if member.activities:
                for activity in member.activities:
                    if isinstance(activity, discord.Streaming):
                        is_streaming = True
                        break

            if is_streaming:
                current_streamers.add(member.id)

                # Check if it's time to award points for this streamer
                last_award = db.get_last_award_time(guild.id, member.id)
                interval = db.get_streamer_earn_interval(guild.id, member.id)

                if now - last_award < interval:
                    continue

                # Check voice channels for viewers
                if member.voice and member.voice.channel:
                    channel = member.voice.channel

                    # Award points to all other members in the channel
                    awarded = False
                    for viewer in channel.members:
                        if viewer.id == member.id or viewer.bot:
                            continue

                        # Track viewer
                        db.add_stream_viewer(guild.id, member.id, viewer.id)

                        # Award points
                        earn_rate = db.get_streamer_earn_rate(guild.id, member.id)
                        db.add_user_points(guild.id, viewer.id, member.id, earn_rate)
                        awarded = True

                        logger.debug(
                            f"Awarded {earn_rate} points to {viewer.id} "
                            f"for watching {member.id} in {guild.id}"
                        )
                    
                    if awarded:
                        db.set_last_award_time(guild.id, member.id, now)

        # Clean up viewers for streamers who stopped streaming
        active_streams = db.get_all_active_streams(guild.id)
        for streamer_id in active_streams:
            if streamer_id not in current_streamers:
                db.clear_stream_viewers(guild.id, streamer_id)

    @discord.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        """Handle voice channel join/leave events"""
        if member.bot:
            return

        # Check if member left a voice channel
        if before.channel and not after.channel:
            # Remove from all stream viewer lists
            for streamer_id in db.get_all_active_streams(member.guild.id):
                db.remove_stream_viewer(member.guild.id, streamer_id, member.id)

        # Check if member changed channels
        elif before.channel != after.channel:
            # Remove from old channel's streams
            if before.channel:
                for streamer_id in db.get_all_active_streams(member.guild.id):
                    db.remove_stream_viewer(member.guild.id, streamer_id, member.id)

    @discord.slash_command(name="viewers", description="Show who's watching a stream")
    @option("streamer", discord.Member, description="Streamer to check (optional)", required=False)
    async def show_viewers(self, ctx: discord.ApplicationContext, streamer: discord.Member = None):
        """Show who's watching a stream"""
        await ctx.defer()

        target = streamer or ctx.author

        viewers = db.get_stream_viewers(ctx.guild.id, target.id)

        if not viewers:
            await ctx.respond(f"❌ No one is watching {target.display_name}'s stream right now!")
            return

        viewer_mentions = []
        for viewer_id in viewers:
            viewer = ctx.guild.get_member(viewer_id)
            if viewer:
                viewer_mentions.append(viewer.mention)

        if not viewer_mentions:
            await ctx.respond(f"❌ No one is watching {target.display_name}'s stream right now!")
            return

        point_name = db.get_streamer_point_name(ctx.guild.id, target.id)

        embed = discord.Embed(
            title=f"👀 Watching {target.display_name}",
            description=f"{len(viewer_mentions)} viewers earning {point_name}:\n" + "\n".join(viewer_mentions),
            color=discord.Color.purple()
        )

        await ctx.respond(embed=embed)

    @discord.slash_command(name="streams", description="Show all active streams in the server")
    async def show_streams(self, ctx: discord.ApplicationContext):
        """Show all active streams in the server"""
        await ctx.defer()

        active_streamers = []

        for member in ctx.guild.members:
            if member.bot:
                continue

            is_streaming = False
            if member.activities:
                for activity in member.activities:
                    if isinstance(activity, discord.Streaming):
                        is_streaming = True
                        break

            if is_streaming:
                viewers = db.get_stream_viewers(ctx.guild.id, member.id)
                point_name = db.get_streamer_point_name(ctx.guild.id, member.id)
                active_streamers.append((member, len(viewers), point_name))

        if not active_streamers:
            await ctx.respond("❌ No one is streaming right now!")
            return

        lines = []
        for streamer, viewer_count, point_name in active_streamers:
            lines.append(
                f"🔴 **{streamer.display_name}** - "
                f"{viewer_count} viewers earning {point_name}"
            )

        embed = discord.Embed(
            title="🎮 Live Streams",
            description="\n".join(lines),
            color=discord.Color.red()
        )

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Streams(bot))