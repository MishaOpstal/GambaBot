from datetime import datetime, timedelta
from typing import Optional, List
import uuid

import discord
from discord.ext import tasks
from discord.commands import SlashCommandGroup, option
from discord.ui import Select, View

from database import db
from helpers.calculation_helper import calculate_percentages, calculate_winnings
from helpers.format_helper import format_time


class BetView(View):
    """Interactive bet placement view with dropdowns"""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.guild_id = guild_id
        self.user_id = user_id
        self.selected_prediction_id = None
        self.selected_side = None
        self.selected_amount = None
        self.selected_streamer_id = None

        # Add prediction selector
        self.add_item(self.create_prediction_select())

    def create_prediction_select(self) -> Select:
        """Create dropdown for selecting a prediction"""
        predictions = db.get_all_guild_predictions(self.guild_id)

        if not predictions:
            # No predictions available
            select = Select(
                placeholder="No active predictions available",
                options=[discord.SelectOption(label="None", value="none")],
                disabled=True
            )
        else:
            options = []
            for pred_id, prediction in list(predictions.items())[:25]:  # Discord limit
                if prediction.get('closed'):
                    continue

                # Truncate question if too long
                question = prediction['question']
                if len(question) > 100:
                    question = question[:97] + "..."

                options.append(discord.SelectOption(
                    label=f"{pred_id[:8]}: {question[:50]}",
                    value=pred_id,
                    description=f"✅ {prediction['believe_answer'][:25]} | ❌ {prediction['doubt_answer'][:25]}"
                ))

            select = Select(
                placeholder="Choose a prediction to bet on",
                options=options,
                custom_id="prediction_select"
            )

        async def callback(interaction: discord.Interaction):
            if select.values[0] == "none":
                return

            self.selected_prediction_id = select.values[0]
            prediction = db.get_prediction(self.guild_id, self.selected_prediction_id)

            # Check if user already bet
            existing_bet = db.get_bet(self.guild_id, self.selected_prediction_id, self.user_id)
            if existing_bet:
                await interaction.response.send_message("❌ You've already placed a bet on this prediction!",
                                                        ephemeral=True)
                return

            # Add side selector
            self.clear_items()
            self.add_item(self.create_side_select(prediction))
            await interaction.response.edit_message(view=self)

        select.callback = callback
        return select

    def create_side_select(self, prediction: dict) -> Select:
        """Create dropdown for selecting believe/doubt"""
        select = Select(
            placeholder="Choose your side",
            options=[
                discord.SelectOption(
                    label=f"✅ Believe: {prediction['believe_answer']}",
                    value="believe",
                    emoji="✅"
                ),
                discord.SelectOption(
                    label=f"❌ Doubt: {prediction['doubt_answer']}",
                    value="doubt",
                    emoji="❌"
                )
            ],
            custom_id="side_select"
        )

        async def callback(interaction: discord.Interaction):
            self.selected_side = select.values[0]

            # Get user's available points
            all_points = db.get_all_user_points(self.guild_id, self.user_id)
            if not all_points:
                await interaction.response.send_message("❌ You don't have any points yet! Watch some streams first.",
                                                        ephemeral=True)
                return

            # Add streamer selector
            self.clear_items()
            self.add_item(self.create_streamer_select(all_points))
            await interaction.response.edit_message(view=self)

        select.callback = callback
        return select

    def create_streamer_select(self, all_points: dict) -> Select:
        """Create dropdown for selecting which streamer's points to use"""
        from bot import PredictionBot
        bot = None
        for client in discord.utils._get_running_loop().run_until_complete(
                discord.utils.maybe_coroutine(
                    lambda: [b for b in discord.Client.__subclasses__() if isinstance(b, PredictionBot)])
        ):
            bot = client
            break

        # This is a workaround - we'll get the guild from the interaction instead
        options = []
        for streamer_id, points in list(all_points.items())[:25]:
            point_name = db.get_streamer_point_name(self.guild_id, streamer_id)
            options.append(discord.SelectOption(
                label=f"User {streamer_id}",
                value=str(streamer_id),
                description=f"{points} {point_name} available"
            ))

        select = Select(
            placeholder="Choose which points to use",
            options=options,
            custom_id="streamer_select"
        )

        async def callback(interaction: discord.Interaction):
            self.selected_streamer_id = int(select.values[0])
            user_points = db.get_user_points(self.guild_id, self.user_id, self.selected_streamer_id)

            # Add amount selector
            self.clear_items()
            self.add_item(self.create_amount_select(user_points))
            await interaction.response.edit_message(view=self)

        select.callback = callback
        return select

    def create_amount_select(self, max_points: int) -> Select:
        """Create dropdown for selecting bet amount"""
        options = []

        # Create preset amounts
        presets = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        for amount in presets:
            if amount <= max_points:
                options.append(discord.SelectOption(
                    label=f"{amount} points",
                    value=str(amount)
                ))

        # Add "All in" option
        if max_points not in presets:
            options.append(discord.SelectOption(
                label=f"All in ({max_points} points)",
                value=str(max_points),
                emoji="🎰"
            ))

        if not options:
            options.append(discord.SelectOption(
                label="Not enough points",
                value="0"
            ))

        select = Select(
            placeholder=f"Choose bet amount (Max: {max_points})",
            options=options[:25],  # Discord limit
            custom_id="amount_select"
        )

        async def callback(interaction: discord.Interaction):
            self.selected_amount = int(select.values[0])

            if self.selected_amount <= 0:
                await interaction.response.send_message("❌ Invalid bet amount!", ephemeral=True)
                return

            # Place the bet
            await self.place_bet(interaction)

        select.callback = callback
        return select

    async def place_bet(self, interaction: discord.Interaction):
        """Actually place the bet"""
        # Deduct points
        current_points = db.get_user_points(self.guild_id, self.user_id, self.selected_streamer_id)
        db.set_user_points(self.guild_id, self.user_id, self.selected_streamer_id,
                           current_points - self.selected_amount)

        # Place bet
        db.place_bet(self.guild_id, self.selected_prediction_id, self.user_id, self.selected_side, self.selected_amount)

        # Get prediction details
        prediction = db.get_prediction(self.guild_id, self.selected_prediction_id)

        # Get bet statistics
        all_bets = db.get_all_bets(self.guild_id, self.selected_prediction_id)
        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}

        believe_pct, doubt_pct = calculate_percentages(believe_bets, doubt_bets)

        # Get streamer info
        streamer = interaction.guild.get_member(self.selected_streamer_id)
        streamer_name = streamer.display_name if streamer else f"User {self.selected_streamer_id}"
        point_name = db.get_streamer_point_name(self.guild_id, self.selected_streamer_id)

        side_emoji = "✅" if self.selected_side == 'believe' else "❌"
        side_name = prediction['believe_answer'] if self.selected_side == 'believe' else prediction['doubt_answer']

        embed = discord.Embed(
            title=f"{side_emoji} Bet Placed!",
            description=f"You bet **{self.selected_amount} {streamer_name}'s {point_name}** on **{side_name}**",
            color=discord.Color.green()
        )
        embed.add_field(name="🆔 Prediction ID", value=f"`{self.selected_prediction_id}`", inline=False)
        embed.add_field(
            name="📊 Current Pool",
            value=f"✅ Believe: {believe_pct}% ({len(believe_bets)} bets, {sum(believe_bets.values())} points)\n"
                  f"❌ Doubt: {doubt_pct}% ({len(doubt_bets)} bets, {sum(doubt_bets.values())} points)",
            inline=False
        )

        # Disable all items
        self.clear_items()
        await interaction.response.edit_message(content="Bet successfully placed!", embed=embed, view=None)


class Predictions(discord.Cog):
    """Cog for managing predictions and betting"""

    def __init__(self, bot):
        self.bot = bot
        self.active_timers = {}  # (guild_id, prediction_id) -> end_time
        self.check_timers.start()
        # Resume timers on startup
        self.bot.loop.create_task(self.resume_predictions())

    prediction = SlashCommandGroup("prediction", "Prediction and betting commands")
    authtoken = SlashCommandGroup("authtoken", "Auth token management for web UI")

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
        embed.set_footer(text=f"Use /bet to place your bet!")

        await ctx.respond(embed=embed)

    @discord.slash_command(name="bet", description="Place a bet on an active prediction (interactive)")
    async def place_bet(self, ctx: discord.ApplicationContext):
        """Place a bet using interactive dropdowns"""
        await ctx.defer(ephemeral=True)

        # Create and send the bet view
        view = BetView(ctx.guild.id, ctx.author.id)

        if not view.children or (len(view.children) == 1 and view.children[0].disabled):
            await ctx.respond("❌ No active predictions available to bet on!", ephemeral=True)
            return

        await ctx.respond("Choose your bet:", view=view, ephemeral=True)

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

    @authtoken.command(name="refresh", description="Generate a new auth token for web UI access")
    async def refresh_token(self, ctx: discord.ApplicationContext):
        """Generate a new auth token for the user"""
        await ctx.defer(ephemeral=True)

        token = db.generate_auth_token(ctx.guild.id, ctx.author.id)

        # Try to DM the user
        try:
            dm_embed = discord.Embed(
                title="🔑 Your Web UI Auth Token",
                description=f"Your auth token for **{ctx.guild.name}**:",
                color=discord.Color.green()
            )
            dm_embed.add_field(name="Token", value=f"```{token}```", inline=False)
            dm_embed.add_field(
                name="⚠️ Keep This Secret!",
                value="This token allows access to your predictions. Never share it with anyone!",
                inline=False
            )
            dm_embed.add_field(
                name="Web UI URLs",
                value=f"All predictions: `http://your-domain/{ctx.guild.id}/{token}`\n"
                      f"Specific prediction: `http://your-domain/{ctx.guild.id}/{token}/[prediction_id]`",
                inline=False
            )

            await ctx.author.send(embed=dm_embed)
            await ctx.respond("✅ Token sent to your DMs!", ephemeral=True)
        except discord.Forbidden:
            await ctx.respond(
                f"❌ Couldn't send you a DM! Please enable DMs from server members.\n\n"
                f"Your token: ||`{token}`||\n⚠️ **Keep this secret!**",
                ephemeral=True
            )

    @authtoken.command(name="verify", description="Verify if an auth token is valid")
    @option("token", str, description="The token to verify")
    async def verify_token(self, ctx: discord.ApplicationContext, token: str):
        """Verify an auth token"""
        await ctx.defer(ephemeral=True)

        result = db.verify_auth_token(token)

        if result and result[0] == ctx.guild.id:
            await ctx.respond("✅ Token is valid!", ephemeral=True)
        else:
            await ctx.respond("❌ Token is invalid or not for this server!", ephemeral=True)

    @discord.slash_command(name="webui", description="Get the web UI link for this server")
    async def get_webui_link(self, ctx: discord.ApplicationContext):
        """Get the web UI link for the current guild"""
        await ctx.defer(ephemeral=True)

        # Get server's web UI URL
        # You'll need to configure your actual domain in production
        base_url = "http://localhost:5000"  # Change this to your actual domain

        embed = discord.Embed(
            title="🌐 Web UI Access",
            description=f"Access your predictions for **{ctx.guild.name}**",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Step 1: Get Your Token",
            value="Use `/authtoken refresh` to generate your auth token if you haven't already.",
            inline=False
        )

        embed.add_field(
            name="Step 2: Visit Web UI",
            value=f"[Click here to access Web UI]({base_url}/{ctx.guild.id})",
            inline=False
        )

        embed.add_field(
            name="Step 3: Enter Token",
            value="Paste your auth token on the web page to view your predictions.",
            inline=False
        )

        embed.add_field(
            name="📋 Direct URL",
            value=f"`{base_url}/{ctx.guild.id}`",
            inline=False
        )

        embed.set_footer(text="Keep your auth token secret!")

        await ctx.respond(embed=embed, ephemeral=True)

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