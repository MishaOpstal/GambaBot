from typing import Dict


def format_time(seconds: int) -> str:
    """Format seconds into MM:SS format"""
    minutes, secs = divmod(seconds, 60)
    return f'{minutes:02d}:{secs:02d}'


def format_points_display(guild_id: int, user_points: Dict[int, int], bot) -> str:
    """
    Format user points with streamer names and custom point names
    Returns formatted string for display
    """
    from database import db

    lines = []
    for streamer_id, points in user_points.items():
        try:
            guild = bot.get_guild(guild_id)
            if not guild:
                continue

            streamer = guild.get_member(streamer_id)
            streamer_name = streamer.display_name if streamer else f"User {streamer_id}"
            point_name = db.get_streamer_point_name(guild_id, streamer_id)

            lines.append(f"**{streamer_name}'s {point_name}**: {points}")
        except:
            continue

    return "\n".join(lines) if lines else "No points yet!"
