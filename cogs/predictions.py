from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands, tasks

from database import db
from helpers.calculation_helper import calculate_percentages, calculate_winnings
from helpers.format_helper import format_time


class Predictions(commands.Cog):
    """Cog for managing predictions and betting"""

    def __init__(self, bot):
        self.bot = bot
        self.active_timers = {}  # guild_id -> task
        self.check_timers.start()

    def cog_unload(self):
        self.check_timers.cancel()

    @tasks.loop(seconds=1)
    async def check_timers(self):
        """Check and update prediction timers"""
        current_time = datetime.now()

        for guild_id in list(self.active_timers.keys()):
            prediction = db.get_prediction(guild_id)
            if not prediction:
                del self.active_timers[guild_id]
                continue

            end_time = datetime.fromisoformat(prediction['end_time'])

            if current_time >= end_time:
                # Timer expired
                guild = self.bot.get_guild(guild_id)
                if guild and prediction.get('channel_id'):
                    channel = guild.get_channel(prediction['channel_id'])
                    if channel:
                        await self.close_submissions(channel, guild_id)

                del self.active_timers[guild_id]

    @check_timers.before_loop
    async def before_check_timers(self):
        await self.bot.wait_until_ready()

    @commands.command(name='start', aliases=['predict'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def start_prediction(self, ctx: commands.Context, time_seconds: int, question: str,
                               believe_answer: str, doubt_answer: str):
        """
        Start a new prediction

        Usage: $start <time_in_seconds> "<question>" "<believe_answer>" "<doubt_answer>"
        Example: $start 300 "Will it rain today?" "Yes" "No"
        """
        # Check if prediction already exists
        existing = db.get_prediction(ctx.guild.id)
        if existing:
            await ctx.send("❌ A prediction is already active in this server!")
            return

        if time_seconds < 10 or time_seconds > 3600:
            await ctx.send("❌ Time must be between 10 seconds and 1 hour.")
            return

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
            'closed': False
        }

        db.create_prediction(ctx.guild.id, prediction_data)
        self.active_timers[ctx.guild.id] = True

        embed = discord.Embed(
            title="📊 New Prediction Started!",
            description=f"**{question}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="✅ Believe", value=believe_answer, inline=True)
        embed.add_field(name="❌ Doubt", value=doubt_answer, inline=True)
        embed.add_field(name="⏰ Time Remaining", value=format_time(time_seconds), inline=False)
        embed.set_footer(text="Use $believe <amount> or $doubt <amount> to place your bet!")

        await ctx.send(embed=embed)

    @commands.command(name='believe', aliases=['blv', 'yes'])
    @commands.guild_only()
    async def bet_believe(self, ctx: commands.Context, amount: int, streamer: Optional[discord.Member] = None):
        """
        Bet on the belief side

        Usage: $believe <amount> [@streamer]
        If streamer is not specified, uses your points with the first available streamer
        """
        await self._place_bet(ctx, 'believe', amount, streamer)

    @commands.command(name='doubt', aliases=['dbt', 'no'])
    @commands.guild_only()
    async def bet_doubt(self, ctx: commands.Context, amount: int, streamer: Optional[discord.Member] = None):
        """
        Bet on the doubt side

        Usage: $doubt <amount> [@streamer]
        If streamer is not specified, uses your points with the first available streamer
        """
        await self._place_bet(ctx, 'doubt', amount, streamer)

    @staticmethod
    async def _place_bet(ctx: commands.Context, side: str, amount: int, streamer: Optional[discord.Member]):
        """Internal method to handle betting logic"""
        prediction = db.get_prediction(ctx.guild.id)
        if not prediction:
            await ctx.send("❌ No active prediction in this server!")
            return

        if prediction.get('closed'):
            await ctx.send("❌ Betting is closed for this prediction!")
            return

        # Check if user already bet
        existing_bet = db.get_bet(ctx.guild.id, ctx.author.id)
        if existing_bet:
            await ctx.send("❌ You've already placed a bet on this prediction!")
            return

        if amount <= 0:
            await ctx.send("❌ Bet amount must be positive!")
            return

        # Determine which streamer's points to use
        if streamer is None:
            # Use points from first available streamer
            all_points = db.get_all_user_points(ctx.guild.id, ctx.author.id)
            if not all_points:
                await ctx.send("❌ You don't have any points yet! Watch some streams first.")
                return

            # Find streamer with enough points
            streamer_id = None
            for s_id, points in all_points.items():
                if points >= amount:
                    streamer_id = s_id
                    break

            if streamer_id is None:
                await ctx.send(f"❌ You don't have enough points! You need {amount} points.")
                return
        else:
            streamer_id = streamer.id
            user_points = db.get_user_points(ctx.guild.id, ctx.author.id, streamer_id)

            if user_points < amount:
                point_name = db.get_streamer_point_name(ctx.guild.id, streamer_id)
                await ctx.send(
                    f"❌ You don't have enough {point_name}! "
                    f"You have {user_points} but need {amount}."
                )
                return

        # Deduct points and place bet
        current_points = db.get_user_points(ctx.guild.id, ctx.author.id, streamer_id)
        db.set_user_points(ctx.guild.id, ctx.author.id, streamer_id, current_points - amount)
        db.place_bet(ctx.guild.id, ctx.author.id, side, amount)

        # Get bet statistics
        all_bets = db.get_all_bets(ctx.guild.id)
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
        embed.add_field(
            name="📊 Current Pool",
            value=f"✅ Believe: {believe_pct}% ({len(believe_bets)} bets, {sum(believe_bets.values())} points)\n"
                  f"❌ Doubt: {doubt_pct}% ({len(doubt_bets)} bets, {sum(doubt_bets.values())} points)",
            inline=False
        )

        await ctx.send(embed=embed)

    @commands.command(name='won', aliases=['winner', 'resolve'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def resolve_prediction(self, ctx: commands.Context, winner: str):
        """
        Resolve a prediction and distribute winnings

        Usage: $won <believe|doubt>
        """
        prediction = db.get_prediction(ctx.guild.id)
        if not prediction:
            await ctx.send("❌ No active prediction in this server!")
            return

        winner = winner.lower()
        if winner not in ['believe', 'doubt', 'blv', 'dbt']:
            await ctx.send("❌ Winner must be 'believe' or 'doubt'!")
            return

        # Normalize winner
        winning_side = 'believe' if winner in ['believe', 'blv'] else 'doubt'

        # Get all bets
        all_bets = db.get_all_bets(ctx.guild.id)
        if not all_bets:
            await ctx.send("❌ No bets were placed on this prediction!")
            db.delete_prediction(ctx.guild.id)
            return

        # Separate bets by side
        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}

        winner_bets = believe_bets if winning_side == 'believe' else doubt_bets
        loser_bets = doubt_bets if winning_side == 'believe' else believe_bets

        if not winner_bets:
            await ctx.send("❌ No one bet on the winning side!")
            # Refund losers
            for user_id, bet_data in all_bets.items():
                # Find which streamer's points were used (simplified: refund to first streamer)
                user_points_dict = db.get_all_user_points(ctx.guild.id, user_id)
                if user_points_dict:
                    streamer_id = list(user_points_dict.keys())[0]
                    current = db.get_user_points(ctx.guild.id, user_id, streamer_id)
                    db.set_user_points(ctx.guild.id, user_id, streamer_id, current + bet_data['amount'])

            db.clear_all_bets(ctx.guild.id)
            db.delete_prediction(ctx.guild.id)
            return

        # Calculate winnings
        winnings = calculate_winnings(loser_bets, winner_bets)

        # Distribute winnings
        for user_id, winning_amount in winnings.items():
            # Find which streamer's points were used
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

        await ctx.send(embed=embed)

        # Cleanup
        db.clear_all_bets(ctx.guild.id)
        db.delete_prediction(ctx.guild.id)
        if ctx.guild.id in self.active_timers:
            del self.active_timers[ctx.guild.id]

    @commands.command(name='refund', aliases=['cancel'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def refund_prediction(self, ctx: commands.Context):
        """
        Cancel the prediction and refund all bets

        Usage: $refund
        """
        prediction = db.get_prediction(ctx.guild.id)
        if not prediction:
            await ctx.send("❌ No active prediction in this server!")
            return

        # Refund all bets
        all_bets = db.get_all_bets(ctx.guild.id)
        for user_id, bet_data in all_bets.items():
            # Refund to first available streamer
            user_points_dict = db.get_all_user_points(ctx.guild.id, user_id)
            if user_points_dict:
                streamer_id = list(user_points_dict.keys())[0]
                current = db.get_user_points(ctx.guild.id, user_id, streamer_id)
                db.set_user_points(ctx.guild.id, user_id, streamer_id, current + bet_data['amount'])

        # Cleanup
        db.clear_all_bets(ctx.guild.id)
        db.delete_prediction(ctx.guild.id)
        if ctx.guild.id in self.active_timers:
            del self.active_timers[ctx.guild.id]

        await ctx.send("✅ Prediction cancelled and all bets refunded!")

    @commands.command(name='prediction', aliases=['pred', 'current'])
    @commands.guild_only()
    async def show_prediction(self, ctx: commands.Context):
        """Show the current active prediction"""
        prediction = db.get_prediction(ctx.guild.id)
        if not prediction:
            await ctx.send("❌ No active prediction in this server!")
            return

        # Get bet statistics
        all_bets = db.get_all_bets(ctx.guild.id)
        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}

        believe_pct, doubt_pct = calculate_percentages(believe_bets, doubt_bets)

        # Calculate time remaining
        end_time = datetime.fromisoformat(prediction['end_time'])
        time_remaining = max(0, int((end_time - datetime.now()).total_seconds()))

        status = "🔒 Closed" if prediction.get('closed') else f"⏰ {format_time(time_remaining)}"

        embed = discord.Embed(
            title="📊 Current Prediction",
            description=f"**{prediction['question']}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="✅ Believe", value=prediction['believe_answer'], inline=True)
        embed.add_field(name="❌ Doubt", value=prediction['doubt_answer'], inline=True)
        embed.add_field(name="Status", value=status, inline=False)
        embed.add_field(
            name="📊 Current Pool",
            value=f"✅ Believe: {believe_pct}% ({len(believe_bets)} bets, {sum(believe_bets.values())} points)\n"
                  f"❌ Doubt: {doubt_pct}% ({len(doubt_bets)} bets, {sum(doubt_bets.values())} points)",
            inline=False
        )

        await ctx.send(embed=embed)

    @staticmethod
    async def close_submissions(channel, guild_id: int):
        """Close betting for a prediction"""
        prediction = db.get_prediction(guild_id)
        if not prediction or prediction.get('closed'):
            return

        prediction['closed'] = True
        db.create_prediction(guild_id, prediction)

        embed = discord.Embed(
            title="🔒 Betting Closed!",
            description=f"**{prediction['question']}**\n\nBetting is now closed. Waiting for resolution...",
            color=discord.Color.orange()
        )

        try:
            await channel.send(embed=embed)
        except:
            pass


async def setup(bot):
    await bot.add_cog(Predictions(bot))
