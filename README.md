# Discord Prediction & Streaming Points Bot

A modern Discord bot that allows users to earn points by watching streams and participate in predictions/betting.

## Features

### 🎮 Stream Watching & Points
- Users earn points by watching other users' streams
- Each streamer can set their own custom point name (e.g., "cookies", "bubbles")
- Streamers can configure how many points viewers earn per interval
- Points are tracked separately per streamer, even if they have the same name

### 🎲 Predictions & Betting
- Create predictions with custom questions and time limits
- Users bet points on either "believe" or "doubt" side
- Winners split the loser pool proportionally
- Bets are locked once placed
- Real-time statistics and percentages

### 📊 Statistics (Works in DMs!)
- View your points across all servers
- Check stats for specific servers
- See which servers have active predictions
- List all servers you share with the bot

## Setup

### Prerequisites
- Docker and Docker Compose
- Discord Bot Token

### Installation

1. Clone this repository
2. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` and add your Discord bot token:
   ```
   DISCORD_TOKEN=your_token_here
   ```

4. Start the bot with Docker Compose:
   ```bash
   docker-compose up -d
   ```

5. View logs:
   ```bash
   docker-compose logs -f bot
   ```

### Configuration

Edit `.env` to customize bot settings:

- `DISCORD_TOKEN`: Your Discord bot token (required)
- `REDIS_HOST`: Redis hostname (default: redis)
- `REDIS_PORT`: Redis port (default: 6379)
- `POINTS_EARN_INTERVAL`: How often points are awarded in seconds (default: 300 = 5 minutes)
- `DEFAULT_POINTS_EARN_RATE`: Default points earned per interval (default: 50)
- `DEFAULT_STARTING_POINTS`: Starting points for new users (default: 1000)

### Discord Bot Permissions

Your bot needs the following permissions:
- Read Messages/View Channels
- Send Messages
- Embed Links
- Read Message History
- Use External Emojis
- Connect (for voice channel tracking)
- View Voice Channels

Intents required:
- Server Members Intent
- Presence Intent
- Message Content Intent

## Commands

### Prediction Commands (Guild Only)

#### Admin Commands
- `$start <time_seconds> "<question>" "<believe_answer>" "<doubt_answer>"` - Start a new prediction
  - Example: `$start 300 "Will it rain?" "Yes" "No"`
- `$won <believe|doubt>` - Resolve prediction and distribute winnings
- `$refund` - Cancel prediction and refund all bets
- `$close` - Close betting early

#### User Commands
- `$believe <amount> [@streamer]` - Bet on the believe side
  - If no streamer specified, uses your first available points
- `$doubt <amount> [@streamer]` - Bet on the doubt side
- `$prediction` - Show current active prediction

### Points Commands

#### User Commands
- `$points [@member]` - Show your or someone else's points
- `$setpointname <name>` - Set your custom point name
- `$setpointrate <rate>` - Set your points earning rate
- `$leaderboard [@streamer]` - Show points leaderboard
- `$streamerinfo [@streamer]` - Show streamer's settings

#### Admin Commands
- `$give @member @streamer <amount>` - Give points to a member
- `$take @member @streamer <amount>` - Take points from a member

### Stream Commands

- `$viewers [@streamer]` - Show who's watching a stream
- `$streams` - Show all active streams in the server

### Statistics Commands (Work in DMs!)

- `$mystats [page]` - Show your stats across all servers (paginated)
- `$serverstats [server_name]` - Show your stats for a specific server
- `$activebets` - Show which servers have active predictions
- `$myservers` - List all servers you share with the bot

## How It Works

### Point Earning System

1. When a user starts streaming on Discord (shows as "Live" with purple status)
2. Other users in the same voice channel earn points automatically
3. Points are awarded every `POINTS_EARN_INTERVAL` seconds (default: 5 minutes)
4. Each streamer has their own point currency with a custom name
5. Users accumulate different point types from different streamers

Example:
- Daan streams and calls his points "bubbles"
- Nick streams and calls his points "cookies"
- Misha watches both streams
- Misha earns both "Daan's bubbles" and "Nick's cookies"

### Prediction System

1. Admin creates a prediction with a question and time limit
2. Users bet their points on either "believe" or "doubt" side
3. Bets are locked once placed - no changes allowed
4. When time expires or admin closes manually, betting stops
5. Admin resolves by declaring a winner
6. Winners get their bet back + proportional share of loser pool
7. Losers lose their bet amount

Example:
- Question: "Will the next game be won?"
- Total believe bets: 1000 points (5 people)
- Total doubt bets: 500 points (2 people)
- Believe wins
- Believe bettors split the 500 doubt points proportionally
- Someone who bet 200 believe gets: 200 (original) + 100 (20% of 500) = 300 points

## Architecture

- **bot.py**: Main bot initialization and event handling
- **config.py**: Configuration management from environment variables
- **database.py**: Redis database wrapper with all data operations
- **cogs/**: Modular command groups
  - `predictions.py`: Prediction and betting system
  - `points.py`: Points management and streamer settings
  - `streams.py`: Stream tracking and point awarding
  - `stats.py`: Statistics and DM functionality
- **utils/helpers.py**: Utility functions

### Database Structure (Redis)

- `points:{guild_id}:{user_id}:{streamer_id}` - User's points for specific streamer
- `streamer:{guild_id}:{streamer_id}:point_name` - Streamer's custom point name
- `streamer:{guild_id}:{streamer_id}:earn_rate` - Points earning rate
- `prediction:{guild_id}` - Active prediction data
- `bet:{guild_id}:{user_id}` - User's bet on current prediction
- `stream:{guild_id}:{streamer_id}:viewers` - Set of current stream viewers

## Troubleshooting

### Bot doesn't detect streams
- Ensure Presence Intent is enabled in Discord Developer Portal
- Check that the bot has permission to view voice channels
- Verify the user has "Go Live" status (purple streaming indicator)

### Points not being awarded
- Check Redis connection: `docker-compose logs redis`
- Verify `POINTS_EARN_INTERVAL` in `.env`
- Ensure viewers are in the same voice channel as streamer

### Commands not working in DMs
- Some commands are guild-only (predictions, points management)
- Statistics commands ($mystats, $activebets, etc.) work in DMs

## Development

### Running without Docker

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Start Redis locally:
   ```bash
   redis-server
   ```

3. Update `.env` to point to localhost:
   ```
   REDIS_HOST=localhost
   ```

4. Run the bot:
   ```bash
   python bot.py
   ```

### Adding New Features

1. Create a new cog in `cogs/` directory
2. Add async `setup(bot)` function at the end
3. Bot will automatically load it on startup

## License

MIT License - feel free to modify and use as needed!

## Credits

Modernized and rewritten from the original MongoDB-based prediction bot.