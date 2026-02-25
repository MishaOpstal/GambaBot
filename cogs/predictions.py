from datetime import datetime, timedelta
from typing import Optional, List, Union
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
                if prediction.get('closed') or prediction.get('resolved'):
                    continue

                # Truncate question if too long
                question = prediction['question']
                if len(question) > 100:
                    question = question[:97] + "..."

                options.append(discord.SelectOption(
                    label=f"{pred_id}: {question[:50]}",
                    value=pred_id,
                    description=f"✅ {prediction['believe_answer'][:25]} | ❌ {prediction['doubt_answer'][:25]}"
                ))

            if not options:
                # No open predictions
                select = Select(
                    placeholder="No active predictions available",
                    options=[discord.SelectOption(label="None", value="none")],
                    disabled=True
                )
            else:
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
            self.selected_streamer_id = prediction.get('creator_id')

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

            # Get user's available points for the relevant streamer
            user_points = db.get_user_points(self.guild_id, self.user_id, self.selected_streamer_id)

            if user_points <= 0:
                point_name = db.get_streamer_point_name(self.guild_id, self.selected_streamer_id)
                streamer = interaction.guild.get_member(self.selected_streamer_id)
                streamer_name = streamer.display_name if streamer else f"User {self.selected_streamer_id}"

                await interaction.response.send_message(
                    f"❌ You don't have any of **{streamer_name}'s {point_name}** yet! Watch some of their streams first.",
                    ephemeral=True
                )
                return

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


class StartPredictionModal(discord.ui.Modal):
    """Modal for starting a new prediction"""

    def __init__(self, cog, *args, **kwargs):
        super().__init__(title="Start New Prediction", *args, **kwargs)
        self.cog = cog
        self.add_item(discord.ui.InputText(
            label="Question",
            placeholder="e.g. Will the streamer win this game?",
            min_length=1,
            max_length=256
        ))
        self.add_item(discord.ui.InputText(
            label="Believe Answer",
            placeholder="e.g. Yes",
            value="Believe",
            max_length=100
        ))
        self.add_item(discord.ui.InputText(
            label="Doubt Answer",
            placeholder="e.g. No",
            value="Doubt",
            max_length=100
        ))
        self.add_item(discord.ui.InputText(
            label="Time (seconds)",
            placeholder="300",
            value="300",
            min_length=2,
            max_length=4
        ))

    async def callback(self, interaction: discord.Interaction):
        question = self.children[0].value
        believe_answer = self.children[1].value
        doubt_answer = self.children[2].value
        try:
            time_seconds = int(self.children[3].value)
        except ValueError:
            await interaction.response.send_message("❌ Invalid time format! Must be a number.", ephemeral=True)
            return

        if not (10 <= time_seconds <= 3600):
            await interaction.response.send_message("❌ Time must be between 10 and 3600 seconds.", ephemeral=True)
            return

        # Start the prediction
        await self.cog.start_prediction(interaction, time_seconds, question, believe_answer, doubt_answer)


class PredictionControlView(View):
    """View for managing predictions (refund, resolve, show)"""

    def __init__(self, guild_id: int, cog):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.cog = cog
        self.selected_prediction_id = None

        # Add Start Prediction button
        start_btn = discord.ui.Button(
            label="Start New Prediction",
            style=discord.ButtonStyle.success,
            emoji="➕",
            row=0
        )
        start_btn.callback = self.start_callback
        self.add_item(start_btn)

        # Add prediction selector
        self.add_item(self.create_prediction_select())

    async def start_callback(self, interaction: discord.Interaction):
        """Callback for Start Prediction button"""
        await interaction.response.send_modal(StartPredictionModal(self.cog))

    def create_prediction_select(self) -> Select:
        """Create dropdown for selecting a prediction to manage"""
        predictions = db.get_all_guild_predictions(self.guild_id)

        if not predictions:
            select = Select(
                placeholder="No predictions available to manage",
                options=[discord.SelectOption(label="None", value="none")],
                disabled=True
            )
        else:
            options = []
            # Sort by most recent (end_time)
            sorted_preds = sorted(predictions.items(), key=lambda x: x[1].get('start_time', ''), reverse=True)
            for pred_id, prediction in sorted_preds[:25]:
                status = "🔒 Closed" if prediction.get('closed') else "⏰ Open"
                if prediction.get('resolved'):
                    status = "✅ Resolved"

                question = prediction['question']
                if len(question) > 50:
                    question = question[:47] + "..."

                options.append(discord.SelectOption(
                    label=f"{pred_id}: {question}",
                    value=pred_id,
                    description=f"Status: {status}"
                ))

            select = Select(
                placeholder="Choose a prediction to manage",
                options=options,
                custom_id="manage_prediction_select"
            )

        async def callback(interaction: discord.Interaction):
            if select.values[0] == "none":
                return

            self.selected_prediction_id = select.values[0]
            prediction = db.get_prediction(self.guild_id, self.selected_prediction_id)

            # Update view with management buttons
            self.clear_items()
            self.add_item(self.create_prediction_select())  # Keep the selector

            # Add Resolve Believe button
            resolve_believe = discord.ui.Button(
                label=f"Resolve: {prediction['believe_answer']}",
                style=discord.ButtonStyle.success,
                emoji="✅",
                disabled=prediction.get('resolved', False)
            )

            async def resolve_believe_callback(btn_interaction: discord.Interaction):
                await self.cog.resolve_prediction(btn_interaction, self.selected_prediction_id, "believe")
                self.clear_items()
                self.add_item(self.create_prediction_select())
                await btn_interaction.followup.edit_message(message_id=interaction.message.id, view=self)

            resolve_believe.callback = resolve_believe_callback
            self.add_item(resolve_believe)

            # Add Resolve Doubt button
            resolve_doubt = discord.ui.Button(
                label=f"Resolve: {prediction['doubt_answer']}",
                style=discord.ButtonStyle.danger,
                emoji="❌",
                disabled=prediction.get('resolved', False)
            )

            async def resolve_doubt_callback(btn_interaction: discord.Interaction):
                await self.cog.resolve_prediction(btn_interaction, self.selected_prediction_id, "doubt")
                self.clear_items()
                self.add_item(self.create_prediction_select())
                await btn_interaction.followup.edit_message(message_id=interaction.message.id, view=self)

            resolve_doubt.callback = resolve_doubt_callback
            self.add_item(resolve_doubt)

            # Add Refund button
            refund_btn = discord.ui.Button(
                label="Refund & Cancel",
                style=discord.ButtonStyle.secondary,
                emoji="💰",
                disabled=prediction.get('resolved', False)
            )

            async def refund_callback(btn_interaction: discord.Interaction):
                await self.cog.refund_prediction(btn_interaction, self.selected_prediction_id)
                self.clear_items()
                self.add_item(self.create_prediction_select())
                await btn_interaction.followup.edit_message(message_id=interaction.message.id, view=self)

            refund_btn.callback = refund_callback
            self.add_item(refund_btn)

            # Add Show button
            show_btn = discord.ui.Button(
                label="Show Stats",
                style=discord.ButtonStyle.primary,
                emoji="📊"
            )

            async def show_callback(btn_interaction: discord.Interaction):
                await self.cog.show_prediction(btn_interaction, self.selected_prediction_id)

            show_btn.callback = show_callback
            self.add_item(show_btn)

            await interaction.response.edit_message(view=self)

        select.callback = callback
        return select


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

    @prediction.command(name="manage", description="Manage predictions using an interactive menu")
    @discord.default_permissions(manage_messages=True)
    async def manage_predictions(self, ctx: discord.ApplicationContext):
        """Manage predictions using an interactive menu"""
        await ctx.defer(ephemeral=True)
        view = PredictionControlView(ctx.guild.id, self)
        await ctx.respond("Prediction Management Menu:", view=view, ephemeral=True)

    @prediction.command(name="start", description="Start a new prediction")
    @option("time_seconds", int, description="Duration in seconds (10-3600)", min_value=10, max_value=3600, required=False)
    @option("question", str, description="The prediction question", required=False)
    @option("believe_answer", str, description="The 'believe' (yes) answer", required=False)
    @option("doubt_answer", str, description="The 'doubt' (no) answer", required=False)
    @discord.default_permissions(manage_messages=True)
    async def start_prediction(
            self,
            ctx: Union[discord.ApplicationContext, discord.Interaction],
            time_seconds: Optional[int] = None,
            question: Optional[str] = None,
            believe_answer: Optional[str] = None,
            doubt_answer: Optional[str] = None
    ):
        """Start a new prediction"""
        if time_seconds is None or question is None or believe_answer is None or doubt_answer is None:
            if isinstance(ctx, discord.ApplicationContext):
                await ctx.send_modal(StartPredictionModal(self))
            else:
                await ctx.response.send_modal(StartPredictionModal(self))
            return

        # Handle both ApplicationContext and Interaction
        if isinstance(ctx, discord.ApplicationContext):
            await ctx.defer()
            respond = ctx.respond
            guild_id = ctx.guild.id
            channel_id = ctx.channel.id
            author_id = ctx.author.id
        else:
            if not ctx.response.is_done():
                await ctx.response.defer()
            respond = ctx.followup.send
            guild_id = ctx.guild_id
            channel_id = ctx.channel_id
            author_id = ctx.user.id

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
            'channel_id': channel_id,
            'creator_id': author_id,
            'closed': False,
            'resolved': False
        }

        db.create_prediction(guild_id, prediction_id, prediction_data)
        self.active_timers[(guild_id, prediction_id)] = end_time

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

        await respond(embed=embed)

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
    @option("prediction_id", str, description="The prediction ID to resolve", required=False)
    @option("winner", str, description="Which side won", choices=["believe", "doubt"], required=False)
    @discord.default_permissions(manage_messages=True)
    async def resolve_prediction(self, ctx: Union[discord.ApplicationContext, discord.Interaction], prediction_id: Optional[str] = None, winner: Optional[str] = None):
        """Resolve a prediction and distribute winnings"""
        if prediction_id is None or winner is None:
            if isinstance(ctx, discord.ApplicationContext):
                view = PredictionControlView(ctx.guild.id, self)
                await ctx.respond("Choose a prediction to manage:", view=view, ephemeral=True)
                return
            # If interaction but missing params, we can't do much without more UI
            elif isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
                await ctx.response.send_message("❌ Missing prediction ID or winner.", ephemeral=True)
                return

        # Determine guild_id and respond method
        if isinstance(ctx, discord.ApplicationContext):
            guild_id = ctx.guild.id
            respond = ctx.respond
        else:
            guild_id = ctx.guild_id
            respond = ctx.followup.send

        # Check if already deferred
        try:
            if isinstance(ctx, discord.ApplicationContext):
                await ctx.defer()
            else:
                if not ctx.response.is_done():
                    await ctx.response.defer()
        except (discord.HTTPException, discord.InteractionResponded):
            pass

        prediction = db.get_prediction(guild_id, prediction_id)
        if not prediction:
            await respond(f"❌ No prediction found with ID `{prediction_id}`!")
            return

        if prediction.get('resolved'):
            await respond("❌ This prediction has already been resolved!")
            return

        winning_side = winner

        # Get all bets
        all_bets = db.get_all_bets(guild_id, prediction_id)
        if not all_bets:
            await respond("❌ No bets were placed on this prediction!")
            # Mark as resolved
            prediction['resolved'] = True
            db.create_prediction(guild_id, prediction_id, prediction)
            db.delete_prediction(guild_id, prediction_id)
            return

        # Separate bets by side
        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}

        winner_bets = believe_bets if winning_side == 'believe' else doubt_bets
        loser_bets = doubt_bets if winning_side == 'believe' else believe_bets

        if not winner_bets:
            await respond("❌ No one bet on the winning side!")
            # Refund losers
            for user_id, bet_data in all_bets.items():
                user_points_dict = db.get_all_user_points(guild_id, user_id)
                if user_points_dict:
                    streamer_id = list(user_points_dict.keys())[0]
                    current = db.get_user_points(guild_id, user_id, streamer_id)
                    db.set_user_points(guild_id, user_id, streamer_id, current + bet_data['amount'])

            db.clear_all_bets(guild_id, prediction_id)
            db.delete_prediction(guild_id, prediction_id)
            if (guild_id, prediction_id) in self.active_timers:
                del self.active_timers[(guild_id, prediction_id)]
            return

        # Calculate winnings
        winnings = calculate_winnings(loser_bets, winner_bets)

        # Distribute winnings
        for user_id, winning_amount in winnings.items():
            user_points_dict = db.get_all_user_points(guild_id, user_id)
            if user_points_dict:
                streamer_id = list(user_points_dict.keys())[0]
                current = db.get_user_points(guild_id, user_id, streamer_id)
                db.set_user_points(guild_id, user_id, streamer_id, current + winning_amount)

        # Find the biggest winner
        biggest_winner_id = max(winnings, key=winnings.get)
        biggest_winner_amount = winnings[biggest_winner_id]
        
        # Try to get member from guild
        guild = self.bot.get_guild(guild_id)
        biggest_winner = guild.get_member(biggest_winner_id) if guild else None

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

        await respond(embed=embed)

        # Cleanup
        db.clear_all_bets(guild_id, prediction_id)
        db.delete_prediction(guild_id, prediction_id)
        if (guild_id, prediction_id) in self.active_timers:
            del self.active_timers[(guild_id, prediction_id)]

    @prediction.command(name="refund", description="Cancel a prediction and refund all bets")
    @option("prediction_id", str, description="The prediction ID to refund", required=False)
    @discord.default_permissions(manage_messages=True)
    async def refund_prediction(self, ctx: Union[discord.ApplicationContext, discord.Interaction], prediction_id: Optional[str] = None):
        """Cancel the prediction and refund all bets"""
        if prediction_id is None:
            if isinstance(ctx, discord.ApplicationContext):
                view = PredictionControlView(ctx.guild.id, self)
                await ctx.respond("Choose a prediction to manage:", view=view, ephemeral=True)
                return
            elif isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
                await ctx.response.send_message("❌ Missing prediction ID.", ephemeral=True)
                return

        # Determine guild_id and respond method
        if isinstance(ctx, discord.ApplicationContext):
            guild_id = ctx.guild.id
            respond = ctx.respond
        else:
            guild_id = ctx.guild_id
            respond = ctx.followup.send

        # Check if already deferred
        try:
            if isinstance(ctx, discord.ApplicationContext):
                await ctx.defer()
            else:
                if not ctx.response.is_done():
                    await ctx.response.defer()
        except (discord.HTTPException, discord.InteractionResponded):
            pass

        prediction = db.get_prediction(guild_id, prediction_id)
        if not prediction:
            await respond(f"❌ No prediction found with ID `{prediction_id}`!")
            return

        # Refund all bets
        all_bets = db.get_all_bets(guild_id, prediction_id)
        for user_id, bet_data in all_bets.items():
            user_points_dict = db.get_all_user_points(guild_id, user_id)
            if user_points_dict:
                streamer_id = list(user_points_dict.keys())[0]
                current = db.get_user_points(guild_id, user_id, streamer_id)
                db.set_user_points(guild_id, user_id, streamer_id, current + bet_data['amount'])

        # Cleanup
        db.clear_all_bets(guild_id, prediction_id)
        db.delete_prediction(guild_id, prediction_id)
        if (guild_id, prediction_id) in self.active_timers:
            del self.active_timers[(guild_id, prediction_id)]

        await respond(f"✅ Prediction `{prediction_id}` cancelled and all bets refunded!")

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
    @option("prediction_id", str, description="The prediction ID to show", required=False)
    async def show_prediction(self, ctx: Union[discord.ApplicationContext, discord.Interaction], prediction_id: Optional[str] = None):
        """Show a specific prediction"""
        if prediction_id is None:
            if isinstance(ctx, discord.ApplicationContext):
                view = PredictionControlView(ctx.guild.id, self)
                await ctx.respond("Choose a prediction to show:", view=view, ephemeral=True)
                return
            elif isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
                await ctx.response.send_message("❌ Missing prediction ID.", ephemeral=True)
                return

        # Determine guild_id, respond method and user_id
        if isinstance(ctx, discord.ApplicationContext):
            guild_id = ctx.guild.id
            respond = ctx.respond
            author_id = ctx.author.id
        else:
            guild_id = ctx.guild_id
            respond = ctx.followup.send
            author_id = ctx.user.id

        # Check if already deferred
        try:
            if isinstance(ctx, discord.ApplicationContext):
                await ctx.defer()
            else:
                if not ctx.response.is_done():
                    await ctx.response.defer()
        except (discord.HTTPException, discord.InteractionResponded):
            pass

        prediction = db.get_prediction(guild_id, prediction_id)
        if not prediction:
            await respond(f"❌ No prediction found with ID `{prediction_id}`!")
            return

        # Get bet statistics
        all_bets = db.get_all_bets(guild_id, prediction_id)
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
        user_bet = db.get_bet(guild_id, prediction_id, author_id)
        if user_bet:
            embed.add_field(
                name="Your Bet",
                value=f"You bet **{user_bet['amount']}** on **{user_bet['side']}**",
                inline=False
            )

        await respond(embed=embed)

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