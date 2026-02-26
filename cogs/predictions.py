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
from config import Config


class BetView(View):
    """Interactive bet placement view with dropdowns"""

    def __init__(self, guild_id: int, cog, user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
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
            select = Select(
                placeholder="No active predictions available",
                options=[discord.SelectOption(label="None", value="none")],
                disabled=True
            )
        else:
            options = []
            for pred_id, prediction in list(predictions.items())[:25]:
                if prediction.get('closed') or prediction.get('resolved'):
                    continue

                question = prediction['question']
                if len(question) > 100:
                    question = question[:97] + "..."

                options.append(discord.SelectOption(
                    label=f"{pred_id}: {question[:50]}",
                    value=pred_id,
                    description=f"✅ {prediction['believe_answer'][:25]} | ❌ {prediction['doubt_answer'][:25]}"
                ))

            if not options:
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
            self.selected_streamer_id = prediction.get('streamer_id') or prediction.get('creator_id')

            existing_bet = db.get_bet(self.guild_id, self.selected_prediction_id, self.user_id)
            if existing_bet:
                await interaction.response.send_message("❌ You've already placed a bet on this prediction!",
                                                        ephemeral=True)
                return

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

            self.clear_items()
            self.add_item(self.create_amount_select(user_points))
            await interaction.response.edit_message(view=self)

        select.callback = callback
        return select

    def create_amount_select(self, max_points: int) -> Select:
        """Create dropdown for selecting bet amount"""
        options = []

        presets = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        for amount in presets:
            if amount <= max_points:
                options.append(discord.SelectOption(
                    label=f"{amount} points",
                    value=str(amount)
                ))

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
            options=options[:25],
            custom_id="amount_select"
        )

        async def callback(interaction: discord.Interaction):
            self.selected_amount = int(select.values[0])

            if self.selected_amount <= 0:
                await interaction.response.send_message("❌ Invalid bet amount!", ephemeral=True)
                return

            await self.place_bet(interaction)

        select.callback = callback
        return select

    async def place_bet(self, interaction: discord.Interaction):
        """Actually place the bet"""
        await self.cog.do_place_bet(
            self.guild_id,
            self.user_id,
            self.selected_prediction_id,
            self.selected_side,
            self.selected_amount,
            interaction
        )


class StreamerSelectView(View):
    """View for selecting a streamer for a prediction"""

    def __init__(self, streamers: List[discord.Member], cog, time_seconds=None, question=None, believe_answer=None, doubt_answer=None):
        super().__init__(timeout=60)
        self.cog = cog
        self.time_seconds = time_seconds
        self.question = question
        self.believe_answer = believe_answer
        self.doubt_answer = doubt_answer

        options = [
            discord.SelectOption(
                label=s.display_name,
                value=str(s.id),
                description=f"Create prediction for {s.display_name}"
            )
            for s in streamers[:25]
        ]

        select = Select(
            placeholder="Choose which streamer this is for",
            options=options
        )

        async def callback(interaction: discord.Interaction):
            streamer_id = int(select.values[0])
            streamer_name = "Streamer"
            for opt in select.options:
                if opt.value == select.values[0]:
                    streamer_name = opt.label
                    break

            if self.question and self.time_seconds:
                await self.cog.do_start_prediction(
                    interaction.guild_id,
                    interaction.channel_id,
                    interaction.user.id,
                    streamer_id,
                    self.time_seconds,
                    self.question,
                    self.believe_answer,
                    self.doubt_answer,
                    interaction
                )
            else:
                await interaction.response.send_modal(
                    StartPredictionModal(self.cog, streamer_id=streamer_id, streamer_name=streamer_name)
                )

        select.callback = callback
        self.add_item(select)


class StartPredictionModal(discord.ui.Modal):
    """Modal for starting a new prediction"""

    def __init__(self, cog, streamer_id: int, streamer_name: str = "Streamer", *args, **kwargs):
        super().__init__(title=f"New Prediction: {streamer_name}", *args, **kwargs)
        self.cog = cog
        self.streamer_id = streamer_id
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
        target_streamer_id = self.streamer_id

        try:
            time_seconds = int(self.children[3].value)
        except ValueError:
            await interaction.response.send_message("❌ Invalid time format! Must be a number.", ephemeral=True)
            return

        if not (10 <= time_seconds <= 3600):
            await interaction.response.send_message("❌ Time must be between 10 and 3600 seconds.", ephemeral=True)
            return

        await self.cog.do_start_prediction(
            interaction.guild_id,
            interaction.channel_id,
            interaction.user.id,
            target_streamer_id,
            time_seconds,
            question,
            believe_answer,
            doubt_answer,
            interaction
        )


class PredictionControlView(View):
    """View for managing predictions (refund, resolve, show)"""

    def __init__(self, guild_id: int, cog, member: discord.Member):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.cog = cog
        self.member = member
        self.selected_prediction_id = None

        start_btn = discord.ui.Button(
            label="Start New Prediction",
            style=discord.ButtonStyle.success,
            emoji="➕",
            row=0
        )
        start_btn.callback = self.start_callback
        self.add_item(start_btn)

        self.add_item(self.create_prediction_select())

    async def start_callback(self, interaction: discord.Interaction):
        """Callback for Start Prediction button"""
        eligible = self.cog.get_eligible_streamers(interaction.guild, self.member)

        if not eligible:
            await interaction.response.send_message(
                "❌ You don't have permission to start predictions for anyone!",
                ephemeral=True
            )
            return

        if len(eligible) == 1:
            await interaction.response.send_modal(
                StartPredictionModal(self.cog, streamer_id=eligible[0].id, streamer_name=eligible[0].display_name)
            )
        else:
            await interaction.response.send_message(
                "Choose which streamer you are starting this prediction for:",
                view=StreamerSelectView(eligible, self.cog),
                ephemeral=True
            )

    def create_prediction_select(self) -> Select:
        """Create dropdown for selecting a prediction to manage"""
        predictions = db.get_all_guild_predictions(self.guild_id)

        predictions = {pid: p for pid, p in predictions.items() if self.cog.can_manage_prediction(self.member, pid, p)}

        if not predictions:
            select = Select(
                placeholder="No predictions available to manage",
                options=[discord.SelectOption(label="None", value="none")],
                disabled=True
            )
        else:
            options = []
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

            self.clear_items()
            self.add_item(self.create_prediction_select())

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
        self.bot.loop.create_task(self.resume_predictions())

    prediction = SlashCommandGroup("prediction", "Prediction and betting commands")
    managers = prediction.create_subgroup("managers", "Manage who can create predictions in your name")
    authtoken = SlashCommandGroup("authtoken", "Auth token management for web UI")

    @managers.command(name="add", description="Allow a user to create predictions in your name")
    @option("member", discord.Member, description="The user to allow")
    async def add_manager(self, ctx: discord.ApplicationContext, member: discord.Member):
        db.add_prediction_manager(ctx.guild.id, ctx.author.id, member.id)
        await ctx.respond(f"✅ {member.mention} can now create predictions in your name!", ephemeral=True)

    @managers.command(name="remove", description="Remove a user's ability to create predictions in your name")
    @option("member", discord.Member, description="The user to remove")
    async def remove_manager(self, ctx: discord.ApplicationContext, member: discord.Member):
        db.remove_prediction_manager(ctx.guild.id, ctx.author.id, member.id)
        await ctx.respond(f"✅ {member.mention} can no longer create predictions in your name!", ephemeral=True)

    @managers.command(name="list", description="List users allowed to create predictions in your name")
    async def list_managers(self, ctx: discord.ApplicationContext):
        managers = db.get_prediction_managers(ctx.guild.id, ctx.author.id)
        if not managers:
            await ctx.respond("❌ You haven't allowed anyone to create predictions in your name yet.", ephemeral=True)
            return

        mentions = []
        for m_id in managers:
            member = ctx.guild.get_member(m_id)
            if member:
                mentions.append(member.mention)
            else:
                mentions.append(f"User ID: {m_id}")

        await ctx.respond(
            f"📋 **Users allowed to create predictions in your name:**\n" + "\n".join(mentions),
            ephemeral=True
        )

    def get_eligible_streamers(self, guild: discord.Guild, user: discord.Member) -> List[discord.Member]:
        """Get list of streamers a user is allowed to manage predictions for"""
        eligible_ids = {user.id}

        managed_streamers = db.get_managed_streamers(guild.id, user.id)
        eligible_ids.update(managed_streamers)

        if user.guild_permissions.manage_messages:
            active_streamer_ids = db.get_all_active_streams(guild.id)
            eligible_ids.update(active_streamer_ids)

            known_streamer_ids = db.get_all_known_streamers(guild.id)
            eligible_ids.update(known_streamer_ids)

        members = []
        for s_id in eligible_ids:
            member = guild.get_member(s_id)
            if member:
                members.append(member)

        members.sort(key=lambda x: x.display_name.lower())
        return members

    def can_manage_prediction(self, member: discord.Member, prediction_id: str, prediction: dict = None) -> bool:
        """Check if a member is allowed to manage a specific prediction"""
        if member.guild_permissions.manage_messages:
            return True

        if prediction is None:
            prediction = db.get_prediction(member.guild.id, prediction_id)

        if not prediction:
            return False

        streamer_id = prediction.get('streamer_id') or prediction.get('creator_id')

        if member.id == streamer_id:
            return True

        if db.is_prediction_manager(member.guild.id, streamer_id, member.id):
            return True

        return False

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

                if datetime.now() < end_time and not prediction.get('closed'):
                    self.active_timers[(guild_id, prediction_id)] = end_time
                    resumed_count += 1
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
    async def manage_predictions(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        view = PredictionControlView(ctx.guild.id, self, ctx.author)
        await ctx.respond("Prediction Management Menu:", view=view, ephemeral=True)

    @prediction.command(name="start", description="Start a new prediction")
    @option("streamer", discord.Member, description="The streamer to create the prediction for", required=False)
    @option("time_seconds", int, description="Duration in seconds (10-3600)", min_value=10, max_value=3600, required=False)
    @option("question", str, description="The prediction question", required=False)
    @option("believe_answer", str, description="The 'believe' (yes) answer", required=False)
    @option("doubt_answer", str, description="The 'doubt' (no) answer", required=False)
    async def start_prediction(
            self,
            ctx: discord.ApplicationContext,
            streamer: Optional[discord.Member] = None,
            time_seconds: Optional[int] = None,
            question: Optional[str] = None,
            believe_answer: Optional[str] = None,
            doubt_answer: Optional[str] = None
    ):
        eligible = self.get_eligible_streamers(ctx.guild, ctx.author)

        if not eligible:
            await ctx.respond("❌ You don't have permission to start predictions for anyone!", ephemeral=True)
            return

        if streamer:
            if streamer not in eligible:
                await ctx.respond(f"❌ You don't have permission to start predictions for {streamer.mention}!", ephemeral=True)
                return

            target_streamer_id = streamer.id
            target_streamer_name = streamer.display_name
        else:
            if len(eligible) == 1:
                target_streamer_id = eligible[0].id
                target_streamer_name = eligible[0].display_name
            else:
                await ctx.respond(
                    "Choose which streamer you are starting this prediction for:",
                    view=StreamerSelectView(eligible, self, time_seconds, question, believe_answer, doubt_answer),
                    ephemeral=True
                )
                return

        if time_seconds and question and believe_answer and doubt_answer:
            await self.do_start_prediction(
                ctx.guild.id,
                ctx.channel.id,
                ctx.author.id,
                target_streamer_id,
                time_seconds,
                question,
                believe_answer,
                doubt_answer,
                ctx
            )
        else:
            await ctx.send_modal(StartPredictionModal(self, streamer_id=target_streamer_id, streamer_name=target_streamer_name))

    async def do_start_prediction(
            self,
            guild_id: int,
            channel_id: int,
            author_id: int,
            streamer_id: int,
            time_seconds: int,
            question: str,
            believe_answer: str,
            doubt_answer: str,
            ctx: Union[discord.ApplicationContext, discord.Interaction] = None
    ) -> str:
        """Internal method to actually create the prediction. Returns prediction_id."""
        respond = None
        if ctx:
            if isinstance(ctx, discord.ApplicationContext):
                await ctx.defer()
                respond = ctx.respond
            else:
                if not ctx.response.is_done():
                    await ctx.response.defer()
                respond = ctx.followup.send

        prediction_id = str(uuid.uuid4())[:8]

        end_time = datetime.now() + timedelta(seconds=time_seconds)
        prediction_data = {
            'question': question,
            'believe_answer': believe_answer,
            'doubt_answer': doubt_answer,
            'start_time': datetime.now().isoformat(),
            'end_time': end_time.isoformat(),
            'channel_id': channel_id,
            'creator_id': author_id,
            'streamer_id': streamer_id,
            'closed': False,
            'resolved': False
        }

        db.create_prediction(guild_id, prediction_id, prediction_data)
        self.active_timers[(guild_id, prediction_id)] = end_time

        guild = self.bot.get_guild(guild_id)
        if guild:
            point_name = db.get_streamer_point_name(guild_id, streamer_id)
            streamer = guild.get_member(streamer_id)
            streamer_name = streamer.display_name if streamer else f"User {streamer_id}"

            embed = discord.Embed(
                title=f"📊 New Prediction for {streamer_name}!",
                description=f"**{question}**",
                color=discord.Color.blue()
            )
            embed.add_field(name="✅ Believe", value=believe_answer, inline=True)
            embed.add_field(name="❌ Doubt", value=doubt_answer, inline=True)
            embed.add_field(name="⏰ Time Remaining", value=format_time(time_seconds), inline=False)
            embed.add_field(name="🆔 Prediction ID", value=f"`{prediction_id}`", inline=False)
            embed.set_footer(text=f"Use /bet to place your {point_name}!")

            if respond:
                await respond(embed=embed)
            else:
                channel = guild.get_channel(channel_id)
                if channel:
                    await channel.send(embed=embed)

        return prediction_id

    async def do_place_bet(
            self,
            guild_id: int,
            user_id: int,
            prediction_id: str,
            side: str,
            amount: int,
            interaction: discord.Interaction = None
    ):
        """Internal method to actually place a bet."""
        prediction = db.get_prediction(guild_id, prediction_id)
        if not prediction:
            if interaction:
                await interaction.response.send_message("❌ Prediction not found!", ephemeral=True)
            return False, "Prediction not found"

        if prediction.get('closed') or prediction.get('resolved'):
            if interaction:
                await interaction.response.send_message("❌ This prediction is closed for betting!", ephemeral=True)
            return False, "Prediction is closed"

        streamer_id = prediction.get('streamer_id') or prediction.get('creator_id')

        existing_bet = db.get_bet(guild_id, prediction_id, user_id)
        if existing_bet:
            if interaction:
                await interaction.response.send_message("❌ You've already placed a bet on this prediction!", ephemeral=True)
            return False, "Already bet"

        current_points = db.get_user_points(guild_id, user_id, streamer_id)
        if current_points < amount:
            if interaction:
                await interaction.response.send_message("❌ You don't have enough points!", ephemeral=True)
            return False, "Not enough points"

        db.set_user_points(guild_id, user_id, streamer_id, current_points - amount)
        db.place_bet(guild_id, prediction_id, user_id, side, amount)

        all_bets = db.get_all_bets(guild_id, prediction_id)
        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}
        believe_pct, doubt_pct = calculate_percentages(believe_bets, doubt_bets)

        if interaction:
            guild = interaction.guild
            streamer = guild.get_member(streamer_id)
            streamer_name = streamer.display_name if streamer else f"User {streamer_id}"
            point_name = db.get_streamer_point_name(guild_id, streamer_id)

            side_emoji = "✅" if side == 'believe' else "❌"
            side_name = prediction['believe_answer'] if side == 'believe' else prediction['doubt_answer']

            embed = discord.Embed(
                title=f"{side_emoji} Bet Placed!",
                description=f"You bet **{amount} {streamer_name}'s {point_name}** on **{side_name}**",
                color=discord.Color.green()
            )
            embed.add_field(name="🆔 Prediction ID", value=f"`{prediction_id}`", inline=False)
            embed.add_field(
                name="📊 Current Pool",
                value=f"✅ Believe: {believe_pct}% ({len(believe_bets)} bets, {sum(believe_bets.values())} points)\n"
                      f"❌ Doubt: {doubt_pct}% ({len(doubt_bets)} bets, {sum(doubt_bets.values())} points)",
                inline=False
            )

            await interaction.response.edit_message(content="Bet successfully placed!", embed=embed, view=None)

        return True, "Success"

    @discord.slash_command(name="bet", description="Place a bet on an active prediction (interactive)")
    async def place_bet(self, ctx: discord.ApplicationContext):
        """Place a bet using interactive dropdowns"""
        await ctx.defer(ephemeral=True)

        view = BetView(ctx.guild.id, self, ctx.author.id)

        if not view.children or (len(view.children) == 1 and view.children[0].disabled):
            await ctx.respond("❌ No active predictions available to bet on!", ephemeral=True)
            return

        await ctx.respond("Choose your bet:", view=view, ephemeral=True)

    @prediction.command(name="resolve", description="Resolve a prediction and distribute winnings")
    @option("prediction_id", str, description="The prediction ID to resolve", required=False)
    @option("winner", str, description="Which side won", choices=["believe", "doubt"], required=False)
    async def resolve_prediction(self, ctx: Union[discord.ApplicationContext, discord.Interaction], prediction_id: Optional[str] = None, winner: Optional[str] = None):
        """Resolve a prediction and distribute winnings"""
        if prediction_id is None or winner is None:
            if isinstance(ctx, discord.ApplicationContext):
                view = PredictionControlView(ctx.guild.id, self, ctx.author)
                await ctx.respond("Choose a prediction to manage:", view=view, ephemeral=True)
                return
            elif isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
                await ctx.response.send_message("❌ Missing prediction ID or winner.", ephemeral=True)
                return

        if isinstance(ctx, discord.ApplicationContext):
            guild_id = ctx.guild.id
            respond = ctx.respond
        else:
            guild_id = ctx.guild_id
            respond = ctx.followup.send

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

        member = ctx.author if isinstance(ctx, discord.ApplicationContext) else ctx.user
        if not self.can_manage_prediction(member, prediction_id, prediction):
            await respond("❌ You don't have permission to resolve this prediction!", ephemeral=True)
            return

        if prediction.get('resolved'):
            await respond("❌ This prediction has already been resolved!")
            return

        winning_side = winner
        streamer_id = prediction.get('streamer_id') or prediction.get('creator_id')

        all_bets = db.get_all_bets(guild_id, prediction_id)
        if not all_bets:
            await respond("❌ No bets were placed on this prediction!")
            prediction['resolved'] = True
            db.create_prediction(guild_id, prediction_id, prediction)
            # Archive as resolved with no bets
            from web_server import store_resolved_prediction, archive_bets
            archive_bets(guild_id, prediction_id, winning_side)
            store_resolved_prediction(guild_id, prediction_id, prediction, winning_side, 0)
            db.delete_prediction(guild_id, prediction_id)
            return

        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}

        winner_bets = believe_bets if winning_side == 'believe' else doubt_bets
        loser_bets = doubt_bets if winning_side == 'believe' else believe_bets

        if not winner_bets:
            await respond("❌ No one bet on the winning side! Refunding all bets.")
            for user_id, bet_data in all_bets.items():
                current = db.get_user_points(guild_id, int(user_id), streamer_id)
                db.set_user_points(guild_id, int(user_id), streamer_id, current + bet_data['amount'])

            # Archive as cancelled since no winners
            from web_server import store_cancelled_prediction, archive_bets
            archive_bets(guild_id, prediction_id)
            store_cancelled_prediction(guild_id, prediction_id, prediction)
            db.clear_all_bets(guild_id, prediction_id)
            db.delete_prediction(guild_id, prediction_id)
            if (guild_id, prediction_id) in self.active_timers:
                del self.active_timers[(guild_id, prediction_id)]
            return

        winnings = calculate_winnings(loser_bets, winner_bets)

        # Store payout info on each bet before archiving
        for user_id, winning_amount in winnings.items():
            bet_key = f"bet:{guild_id}:{prediction_id}:{user_id}"
            import json
            raw = db.redis.get(bet_key)
            if raw:
                bet_data = json.loads(raw)
                bet_data['payout'] = winning_amount
                db.redis.set(bet_key, json.dumps(bet_data))

        # Distribute winnings
        for user_id, winning_amount in winnings.items():
            current = db.get_user_points(guild_id, int(user_id), streamer_id)
            db.set_user_points(guild_id, int(user_id), streamer_id, current + winning_amount)

        biggest_winner_id = max(winnings, key=winnings.get)
        biggest_winner_amount = winnings[biggest_winner_id]

        guild = self.bot.get_guild(guild_id)
        biggest_winner = guild.get_member(biggest_winner_id) if guild else None

        believe_pct, doubt_pct = calculate_percentages(believe_bets, doubt_bets)

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

        # Archive to history BEFORE cleanup
        from web_server import store_resolved_prediction, archive_bets
        archive_bets(guild_id, prediction_id, winning_side)
        store_resolved_prediction(
            guild_id, prediction_id, prediction,
            winning_side, sum(loser_bets.values())
        )

        # Cleanup
        db.clear_all_bets(guild_id, prediction_id)
        db.delete_prediction(guild_id, prediction_id)
        if (guild_id, prediction_id) in self.active_timers:
            del self.active_timers[(guild_id, prediction_id)]

    @prediction.command(name="refund", description="Cancel a prediction and refund all bets")
    @option("prediction_id", str, description="The prediction ID to refund", required=False)
    async def refund_prediction(self, ctx: Union[discord.ApplicationContext, discord.Interaction], prediction_id: Optional[str] = None):
        """Cancel the prediction and refund all bets"""
        if prediction_id is None:
            if isinstance(ctx, discord.ApplicationContext):
                view = PredictionControlView(ctx.guild.id, self, ctx.author)
                await ctx.respond("Choose a prediction to manage:", view=view, ephemeral=True)
                return
            elif isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
                await ctx.response.send_message("❌ Missing prediction ID.", ephemeral=True)
                return

        if isinstance(ctx, discord.ApplicationContext):
            guild_id = ctx.guild.id
            respond = ctx.respond
        else:
            guild_id = ctx.guild_id
            respond = ctx.followup.send

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

        member = ctx.author if isinstance(ctx, discord.ApplicationContext) else ctx.user
        if not self.can_manage_prediction(member, prediction_id, prediction):
            await respond("❌ You don't have permission to refund this prediction!", ephemeral=True)
            return

        streamer_id = prediction.get('streamer_id') or prediction.get('creator_id')

        all_bets = db.get_all_bets(guild_id, prediction_id)
        for user_id, bet_data in all_bets.items():
            current = db.get_user_points(guild_id, int(user_id), streamer_id)
            db.set_user_points(guild_id, int(user_id), streamer_id, current + bet_data['amount'])

        # Archive to history BEFORE cleanup
        from web_server import store_cancelled_prediction, archive_bets
        archive_bets(guild_id, prediction_id, winner_side=None)
        store_cancelled_prediction(guild_id, prediction_id, prediction)

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
            end_time = datetime.fromisoformat(prediction['end_time'])
            time_remaining = max(0, int((end_time - datetime.now()).total_seconds()))

            status = "🔒 Closed" if prediction.get('closed') else f"⏰ {format_time(time_remaining)}"

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
                view = PredictionControlView(ctx.guild.id, self, ctx.author)
                await ctx.respond("Choose a prediction to show:", view=view, ephemeral=True)
                return
            elif isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
                await ctx.response.send_message("❌ Missing prediction ID.", ephemeral=True)
                return

        if isinstance(ctx, discord.ApplicationContext):
            guild_id = ctx.guild.id
            respond = ctx.respond
            author_id = ctx.author.id
        else:
            guild_id = ctx.guild_id
            respond = ctx.followup.send
            author_id = ctx.user.id

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

        all_bets = db.get_all_bets(guild_id, prediction_id)
        believe_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'believe'}
        doubt_bets = {uid: bet['amount'] for uid, bet in all_bets.items() if bet['side'] == 'doubt'}

        believe_pct, doubt_pct = calculate_percentages(believe_bets, doubt_bets)

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
                name="Web UI URL",
                value=f"`{Config.DOMAIN}/{ctx.guild.id}/{token}`",
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

        base_url = Config.DOMAIN
        port = Config.PORT
        use_https = Config.USE_HTTPS
        use_port_in_url = Config.USE_PORT_IN_URL

        # If not port specified, use only base_url as target_url, otherwise include :port
        if not port or not use_port_in_url:
            if use_https:
                target_url = f"https://{base_url}"
            else:
                target_url = f"http://{base_url}"
        else:
            if use_https:
                target_url = f"https://{base_url}:{port}"
            else:
                target_url = f"http://{base_url}:{port}"

        embed = discord.Embed(
            title="🌐 Web UI Access",
            description=f"Access your predictions for **{ctx.guild.name}**",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Step 1: Get Your Token",
            value="Use `/authtoken refresh` to generate your auth token.",
            inline=False
        )
        embed.add_field(
            name="Step 2: Visit Web UI",
            value=f"[Click here to access Web UI]({target_url}/{ctx.guild.id})",
            inline=False
        )
        embed.add_field(
            name="📋 Direct URL",
            value=f"`{target_url}/{ctx.guild.id}`",
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
        except Exception:
            pass


def setup(bot):
    bot.add_cog(Predictions(bot))