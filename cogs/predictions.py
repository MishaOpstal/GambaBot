from datetime import datetime, timedelta
from typing import Optional
import uuid

import discord
from discord.ext import tasks
from discord.commands import SlashCommandGroup, option

from database import db
from helpers.calculation_helper import calculate_percentages, calculate_winnings
from helpers.format_helper import format_time


class Predictions(discord.Cog):
    """Cog for managing predictions and betting"""

    def __init__(self, bot):
        self.bot = bot
        self.active_timers = {}  # (guild_id, prediction_id) -> end_time
        self.check_timers.start()
        # Resume timers on startup
        self.bot.loop.create_task(self.resume_predictions())

    prediction = SlashCommandGroup("prediction", "Prediction and betting commands")

    def cog_unload(self):
        self.check_timers.cancel()

    async def resume_predictions(self):
        """Resume all active predictions after bot restart"""
        await self.bot.wait_until_ready()

        all_predictions = db.get_all_active_predictions()
        resumed_count = 0

        for guild_id, prediction_ids in all_predictions.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            for prediction_id in prediction_ids:
                prediction = db.get_prediction(guild_id, prediction_id)
                if not prediction:
                    continue

                end_time = datetime.fromisoformat(prediction['end_time'])

                # If prediction hasn't expired yet, resume timer
                if datetime.now() < end_time and not prediction.get('closed'):
                    self.active_timers[(guild_id, prediction_id)] = end_time
                    resumed_count += 1
                # If prediction expired while bot was down, close it now
                elif not prediction.get('closed'):
                    channel = guild.get_channel(prediction.get('channel_id'))
                    if channel:
                        await self.close_submissions(channel, guild_id, prediction_id)
                    resumed_count += 1

        if resumed_count > 0:
            print(f"[Predictions] Resumed {resumed_count} active predictions")

    @tasks.loop(seconds=1)
    async def check_timers(self):
        """Check and update prediction timers"""
        current_time = datetime.now()

        for (guild_id, prediction_id), end_time in list(self.active_timers.items()):
            if current_time >= end_time:
                # Timer expired
                prediction = db.get_prediction(guild_id, prediction_id)
                if not prediction:
                    del self.active_timers[(guild_id, prediction_id)]
                    continue

                guild = self.bot.get_guild(guild_id)
                if guild and prediction.get('channel_id'):
                    channel = guild.get_channel(prediction['channel_id'])
                    if channel:
                        await self.close_submissions(channel, guild_id, prediction_id)

                del self.active_timers[(guild_id, prediction_id)]

    @check_timers.before_loop
    async def before_check_timers(self):
        await self.bot.wait_until_ready()

    @prediction.command(name="start", description="Start a new prediction")
    @option("time_seconds", int, description="Duration in seconds (10-3600)", min_value=10, max_value=3600)
    @option("question", str, description="The prediction question")
    @option("believe_answer", str, description="The 'believe' (yes) answer")
    @option("doubt_answer", str, description="The 'doubt' (no) answer")
    @discord.default_permissions(manage_messages=True)
    async def start_prediction(
            self,
            ctx: discord.ApplicationContext,
            time_seconds: int,
            question: str,
            believe_answer: str,
            doubt_answer: str
    ):
        """Start a new prediction"""
        await ctx.defer()

        # Generate unique prediction ID
        prediction_id = str(uuid.uuid4())[:8]

        # Create prediction
        end_time = datetime.now() + timedelta(seconds=time_seconds)
        prediction_data = {
            'question': question,
            'believe_answer': believe_answer,
            'doubt_answer': doubt_answer,
            'start_time': datetime.now().isoformat(),
            'end_time': end_time.isoformat(),
            'channel_id': ctx.channel.id,
            'creator_id': ctx.author.id,
            'closed': False,
            'resolved': False
        }

        db.create_prediction(ctx.guild.id, prediction_id, prediction_data)
        self.active_timers[(ctx.guild.id, prediction_id)] = end_time

        embed = discord.Embed(
            title="📊 New Prediction Started!",
            description=f"**{question}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="✅ Believe", value=believe_answer, inline=True)
        embed.add_field(name="❌ Doubt", value=doubt_answer, inline=True)
        embed.add_field(name="⏰ Time Remaining", value=format_time(time_seconds), inline=False)
        embed.add_field(name="🆔 Prediction ID", value=f"`{prediction_id}`", inline=False)
        embed.set_footer(text=f"Use /bet to place your bet! Use ID: {prediction_id}")

        await ctx.respond(embed=embed)

    @discord.slash_command(name="bet", description="Place a bet on an active prediction")
    @option("prediction_id", str, description="The prediction ID to bet on")
    @option("side", str, description="Which side to bet on", choices=["believe", "doubt"])
    @option("amount", int, description="Amount of points to bet", min_value=1)
    @option("streamer", discord.Member, description="Which streamer's points to use (optional)", required=False)
    async def place_bet(
            self,
            ctx: discord.ApplicationContext,
            prediction_id: str,
            side: str,
            amount: int,
            streamer: Optional[discord.Member] = None
    ):
        """Place a bet on an active prediction"""
        await ctx.defer(ephemeral=True)

        prediction = db.get_prediction(ctx.guild.id, prediction_id)
        if not prediction:
            await ctx.respond(f"❌ No prediction found with ID `{prediction_id}`!", ephemeral=True)
            return

        if prediction.get('closed'):
            await ctx.respond("❌ Betting is closed for this prediction!", ephemeral=True)
            return

        # Check if user already bet on this prediction
        existing_bet = db.get_bet(ctx.guild.id, prediction_id, ctx.author.id)
        if existing_bet:
            await ctx.respond("❌ You've already placed a bet on this prediction!", ephemeral=True)
            return

        # Determine which streamer's points to use
        if streamer is None:
            # Use points from first available streamer
            all_points = db.get_all_user_points(ctx.guild.id, ctx.author.id)
            if not all_points:
                await ctx.respond("❌ You don't have any points yet! Watch some streams first.", ephemeral=True)
                return

            # Find streamer with enough points
            streamer_id = None
            for s_id, points in all_points.items():
                if points >= amount:
                    streamer_id = s_id
                    break

            if streamer_id is None:
                await ctx.respond(f"❌ You don't have enough points! You need {amount} points.", ephemeral=True)
                return
        else:
            streamer_id = streamer.id
            user_points = db.get_user_points(ctx.guild.id, ctx.author.id, streamer_id)

            if user_points < amount:
                point_name = db.get_streamer_point_name(ctx.guild.id, streamer_id)
                await ctx.respond(
                    f"❌ You don't have enough {point_name}! "
                    f"You have {user_points} but need {amount}.",
                    ephemeral=True
                )
                return

        # Deduct points and place bet
        current_points = db.get_user_points(ctx.guild.id, ctx.author.id, streamer_id)
        db.set_user_points(ctx.guild.id, ctx.author.id, streamer_id, current_points - amount)
        db.place_bet(ctx.guild.id, prediction_id, ctx.author.id, side, amount)

        # Get bet statistics
        all_bets = db.get_all_bets(ctx.guild.id, prediction_id)
        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}

        believe_pct, doubt_pct = calculate_percentages(believe_bets, doubt_bets)

        # Get streamer info
        streamer_member = ctx.guild.get_member(streamer_id)
        streamer_name = streamer_member.display_name if streamer_member else f"User {streamer_id}"
        point_name = db.get_streamer_point_name(ctx.guild.id, streamer_id)

        side_emoji = "✅" if side == 'believe' else "❌"
        side_name = prediction['believe_answer'] if side == 'believe' else prediction['doubt_answer']

        embed = discord.Embed(
            title=f"{side_emoji} Bet Placed!",
            description=f"{ctx.author.mention} bet **{amount} {streamer_name}'s {point_name}** on **{side_name}**",
            color=discord.Color.green()
        )
        embed.add_field(name="🆔 Prediction ID", value=f"`{prediction_id}`", inline=False)
        embed.add_field(
            name="📊 Current Pool",
            value=f"✅ Believe: {believe_pct}% ({len(believe_bets)} bets, {sum(believe_bets.values())} points)\n"
                  f"❌ Doubt: {doubt_pct}% ({len(doubt_bets)} bets, {sum(doubt_bets.values())} points)",
            inline=False
        )

        await ctx.respond(embed=embed)

    @prediction.command(name="resolve", description="Resolve a prediction and distribute winnings")
    @option("prediction_id", str, description="The prediction ID to resolve")
    @option("winner", str, description="Which side won", choices=["believe", "doubt"])
    @discord.default_permissions(manage_messages=True)
    async def resolve_prediction(self, ctx: discord.ApplicationContext, prediction_id: str, winner: str):
        """Resolve a prediction and distribute winnings"""
        await ctx.defer()

        prediction = db.get_prediction(ctx.guild.id, prediction_id)
        if not prediction:
            await ctx.respond(f"❌ No prediction found with ID `{prediction_id}`!")
            return

        if prediction.get('resolved'):
            await ctx.respond("❌ This prediction has already been resolved!")
            return

        winning_side = winner

        # Get all bets
        all_bets = db.get_all_bets(ctx.guild.id, prediction_id)
        if not all_bets:
            await ctx.respond("❌ No bets were placed on this prediction!")
            # Mark as resolved
            prediction['resolved'] = True
            db.create_prediction(ctx.guild.id, prediction_id, prediction)
            db.delete_prediction(ctx.guild.id, prediction_id)
            return

        # Separate bets by side
        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}

        winner_bets = believe_bets if winning_side == 'believe' else doubt_bets
        loser_bets = doubt_bets if winning_side == 'believe' else believe_bets

        if not winner_bets:
            await ctx.respond("❌ No one bet on the winning side!")
            # Refund losers
            for user_id, bet_data in all_bets.items():
                user_points_dict = db.get_all_user_points(ctx.guild.id, user_id)
                if user_points_dict:
                    streamer_id = list(user_points_dict.keys())[0]
                    current = db.get_user_points(ctx.guild.id, user_id, streamer_id)
                    db.set_user_points(ctx.guild.id, user_id, streamer_id, current + bet_data['amount'])

            db.clear_all_bets(ctx.guild.id, prediction_id)
            db.delete_prediction(ctx.guild.id, prediction_id)
            if (ctx.guild.id, prediction_id) in self.active_timers:
                del self.active_timers[(ctx.guild.id, prediction_id)]
            return

        # Calculate winnings
        winnings = calculate_winnings(loser_bets, winner_bets)

        # Distribute winnings
        for user_id, winning_amount in winnings.items():
            user_points_dict = db.get_all_user_points(ctx.guild.id, user_id)
            if user_points_dict:
                streamer_id = list(user_points_dict.keys())[0]
                current = db.get_user_points(ctx.guild.id, user_id, streamer_id)
                db.set_user_points(ctx.guild.id, user_id, streamer_id, current + winning_amount)

        # Find the biggest winner
        biggest_winner_id = max(winnings, key=winnings.get)
        biggest_winner_amount = winnings[biggest_winner_id]
        biggest_winner = ctx.guild.get_member(biggest_winner_id)

        believe_pct, doubt_pct = calculate_percentages(believe_bets, doubt_bets)

        # Create results embed
        winning_answer = prediction['believe_answer'] if winning_side == 'believe' else prediction['doubt_answer']

        embed = discord.Embed(
            title="🎉 Prediction Resolved!",
            description=f"**{prediction['question']}**\n\n**Winner:** {winning_answer}",
            color=discord.Color.gold()
        )
        embed.add_field(name="🆔 Prediction ID", value=f"`{prediction_id}`", inline=False)
        embed.add_field(
            name="📊 Final Pool",
            value=f"✅ Believe: {believe_pct}% ({len(believe_bets)} bets, {sum(believe_bets.values())} points)\n"
                  f"❌ Doubt: {doubt_pct}% ({len(doubt_bets)} bets, {sum(doubt_bets.values())} points)",
            inline=False
        )
        embed.add_field(
            name="👑 Biggest Winner",
            value=f"{biggest_winner.mention if biggest_winner else 'Unknown'} won **{biggest_winner_amount}** points!",
            inline=False
        )

        await ctx.respond(embed=embed)

        # Cleanup
        db.clear_all_bets(ctx.guild.id, prediction_id)
        db.delete_prediction(ctx.guild.id, prediction_id)
        if (ctx.guild.id, prediction_id) in self.active_timers:
            del self.active_timers[(ctx.guild.id, prediction_id)]

    @prediction.command(name="refund", description="Cancel a prediction and refund all bets")
    @option("prediction_id", str, description="The prediction ID to refund")
    @discord.default_permissions(manage_messages=True)
    async def refund_prediction(self, ctx: discord.ApplicationContext, prediction_id: str):
        """Cancel the prediction and refund all bets"""
        await ctx.defer()

        prediction = db.get_prediction(ctx.guild.id, prediction_id)
        if not prediction:
            await ctx.respond(f"❌ No prediction found with ID `{prediction_id}`!")
            return

        # Refund all bets
        all_bets = db.get_all_bets(ctx.guild.id, prediction_id)
        for user_id, bet_data in all_bets.items():
            user_points_dict = db.get_all_user_points(ctx.guild.id, user_id)
            if user_points_dict:
                streamer_id = list(user_points_dict.keys())[0]
                current = db.get_user_points(ctx.guild.id, user_id, streamer_id)
                db.set_user_points(ctx.guild.id, user_id, streamer_id, current + bet_data['amount'])

        # Cleanup
        db.clear_all_bets(ctx.guild.id, prediction_id)
        db.delete_prediction(ctx.guild.id, prediction_id)
        if (ctx.guild.id, prediction_id) in self.active_timers:
            del self.active_timers[(ctx.guild.id, prediction_id)]

        await ctx.respond(f"✅ Prediction `{prediction_id}` cancelled and all bets refunded!")

    @prediction.command(name="list", description="List all active predictions in this server")
    async def list_predictions(self, ctx: discord.ApplicationContext):
        """List all active predictions"""
        await ctx.defer()

        predictions = db.get_all_guild_predictions(ctx.guild.id)

        if not predictions:
            await ctx.respond("❌ No active predictions in this server!")
            return

        embed = discord.Embed(
            title=f"📊 Active Predictions ({len(predictions)})",
            color=discord.Color.blue()
        )

        for pred_id, prediction in predictions.items():
            # Calculate time remaining
            end_time = datetime.fromisoformat(prediction['end_time'])
            time_remaining = max(0, int((end_time - datetime.now()).total_seconds()))

            status = "🔒 Closed" if prediction.get('closed') else f"⏰ {format_time(time_remaining)}"

            # Get bet counts
            all_bets = db.get_all_bets(ctx.guild.id, pred_id)
            total_bets = len(all_bets)
            total_points = sum(bet['amount'] for bet in all_bets.values())

            embed.add_field(
                name=f"ID: `{pred_id}` - {status}",
                value=f"**{prediction['question']}**\n"
                      f"✅ {prediction['believe_answer']} vs ❌ {prediction['doubt_answer']}\n"
                      f"💰 {total_bets} bets, {total_points} points total",
                inline=False
            )

        await ctx.respond(embed=embed)

    @prediction.command(name="show", description="Show details of a specific prediction")
    @option("prediction_id", str, description="The prediction ID to show")
    async def show_prediction(self, ctx: discord.ApplicationContext, prediction_id: str):
        """Show a specific prediction"""
        await ctx.defer()

        prediction = db.get_prediction(ctx.guild.id, prediction_id)
        if not prediction:
            await ctx.respond(f"❌ No prediction found with ID `{prediction_id}`!")
            return

        # Get bet statistics
        all_bets = db.get_all_bets(ctx.guild.id, prediction_id)
        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}

        believe_pct, doubt_pct = calculate_percentages(believe_bets, doubt_bets)

        # Calculate time remaining
        end_time = datetime.fromisoformat(prediction['end_time'])
        time_remaining = max(0, int((end_time - datetime.now()).total_seconds()))

        status = "🔒 Closed" if prediction.get('closed') else f"⏰ {format_time(time_remaining)}"

        embed = discord.Embed(
            title="📊 Prediction Details",
            description=f"**{prediction['question']}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="🆔 ID", value=f"`{prediction_id}`", inline=False)
        embed.add_field(name="✅ Believe", value=prediction['believe_answer'], inline=True)
        embed.add_field(name="❌ Doubt", value=prediction['doubt_answer'], inline=True)
        embed.add_field(name="Status", value=status, inline=False)
        embed.add_field(
            name="📊 Current Pool",
            value=f"✅ Believe: {believe_pct}% ({len(believe_bets)} bets, {sum(believe_bets.values())} points)\n"
                  f"❌ Doubt: {doubt_pct}% ({len(doubt_bets)} bets, {sum(doubt_bets.values())} points)",
            inline=False
        )

        # Show if user has bet
        user_bet = db.get_bet(ctx.guild.id, prediction_id, ctx.author.id)
        if user_bet:
            embed.add_field(
                name="Your Bet",
                value=f"You bet **{user_bet['amount']}** on **{user_bet['side']}**",
                inline=False
            )

        await ctx.respond(embed=embed)

    async def close_submissions(self, channel, guild_id: int, prediction_id: str):
        """Close betting for a prediction"""
        prediction = db.get_prediction(guild_id, prediction_id)
        if not prediction or prediction.get('closed'):
            return

        prediction['closed'] = True
        db.create_prediction(guild_id, prediction_id, prediction)

        embed = discord.Embed(
            title="🔒 Betting Closed!",
            description=f"**{prediction['question']}**\n\nBetting is now closed. Waiting for resolution...",
            color=discord.Color.orange()
        )
        embed.add_field(name="🆔 Prediction ID", value=f"`{prediction_id}`", inline=False)

        try:
            await channel.send(embed=embed)
        except:
            pass


def setup(bot):
    bot.add_cog(Predictions(bot))